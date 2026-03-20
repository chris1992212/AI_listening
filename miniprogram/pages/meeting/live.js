// 会议进行页：录音分片上传、轮询建议、信号灯、震动
const app = getApp();

const CHUNK_INTERVAL_MS = 8000;   // 每 8 秒上传一段
const POLL_INTERVAL_MS = 5000;   // 每 5 秒拉取状态

Page({
  data: {
    meetingId: '',
    topic: '',
    lamp: 'gray',       // gray | yellow | green
    sampleUtterance: '',
    reason: '',
    summary: '',
    shouldSpeak: false,
    llmPriority: 'low',
    recentLines: [],
    lastShouldSpeak: false,
    recording: false,
    lastError: '',
    asrLines: [],
    finalReport: null,
  },

  pushAsrLine(text) {
    const t = (text || '').toString().trim();
    if (!t) return;
    const prev = this.data.asrLines || [];
    const next = prev.concat([t]).slice(-50);
    this.setData({ asrLines: next });
  },

  setError(msg) {
    const text = (msg || '').toString();
    this.setData({ lastError: text });
    if (text) wx.showToast({ title: text.slice(0, 40), icon: 'none' });
  },

  onLoad(options) {
    const meetingId = options.meeting_id || app.globalData.meetingId || '';
    if (!meetingId) {
      wx.showToast({ title: '缺少会议ID', icon: 'none' });
      setTimeout(() => wx.navigateBack(), 1500);
      return;
    }
    this.setData({ meetingId });
    wx.setKeepScreenOn({ keepScreenOn: true });
    this.startRecorder();
    this.startPoll();
  },

  onUnload() {
    this.stopRecorder();
    this.stopPoll();
    wx.setKeepScreenOn({ keepScreenOn: false });
  },

  recorder: null,
  chunkTimer: null,
  pollTimer: null,

  startRecorder() {
    const rec = wx.getRecorderManager();
    this.recorder = rec;
    rec.onStart(() => this.setData({ recording: true }));
    rec.onStop(() => this.setData({ recording: false }));
    rec.onError((e) => {
      console.error('recorder onError', e);
      this.setError(e?.errMsg || '录音异常');
    });

    const start = () => {
      try {
        rec.start({
          duration: CHUNK_INTERVAL_MS,
          sampleRate: 16000,
          numberOfChannels: 1,
          format: 'aac',
        });
      } catch (e) {
        console.error('recorder start error', e);
        this.setError(e?.message || '启动录音失败');
      }
    };

    rec.onStop((res) => {
      const path = res.tempFilePath;
      if (path) this.uploadChunk(path);
      this.chunkTimer = setTimeout(start, 500);
    });

    start();
  },

  stopRecorder() {
    if (this.chunkTimer) clearTimeout(this.chunkTimer);
    this.chunkTimer = null;
    if (this.recorder) {
      try { this.recorder.stop(); } catch (e) {}
      this.recorder = null;
    }
  },

  uploadChunk(tempFilePath) {
    const meetingId = this.data.meetingId;
    const baseUrl = app.globalData.baseUrl;
    wx.uploadFile({
      url: baseUrl + '/api/meeting/chunk',
      filePath: tempFilePath,
      name: 'audio',
      formData: { meeting_id: meetingId },
      success: (res) => {
        if (res.statusCode && res.statusCode >= 400) {
          console.error('uploadFile bad status', res.statusCode, res.data);
          this.setError('上传失败 ' + res.statusCode);
          return;
        }
        // 后端返回：{"ok":true,"text":"..."}
        try {
          const raw = res.data || '';
          const obj = typeof raw === 'string' ? JSON.parse(raw) : raw;
          const text = obj && obj.text ? obj.text : '';
          if (text) this.pushAsrLine(text);
        } catch (e) {
          // 返回非 JSON 时也展示一部分，便于排查
          const raw = (res.data || '').toString();
          if (raw) this.pushAsrLine('[chunk-res] ' + raw.slice(0, 120));
        }
      },
      fail: (err) => {
        console.error('uploadFile fail', err);
        this.setError(err?.errMsg || '上传失败');
      },
    });
  },

  startPoll() {
    const poll = () => {
      const meetingId = this.data.meetingId;
      if (!meetingId) return;
      wx.request({
        url: app.globalData.baseUrl + '/api/meeting/status',
        data: { meeting_id: meetingId },
        timeout: 8000,
        success: (res) => {
          if (res.statusCode !== 200 || !res.data) {
            console.error('status non-200', res.statusCode, res.data);
            this.setError('status错误 ' + res.statusCode);
            return;
          }
          const d = res.data;
          const shouldSpeak = !!d.should_speak;
          const last = this.data.lastShouldSpeak;
          if (shouldSpeak && !last) wx.vibrateShort({ type: 'medium' });
          let lamp = 'gray';
          if (d.priority === 'high' && shouldSpeak) lamp = 'green';
          else if (d.priority === 'medium' || shouldSpeak) lamp = 'yellow';
          this.setData({
            topic: d.topic || this.data.topic,
            lamp,
            sampleUtterance: d.sample_utterance || '',
            reason: d.reason || '',
            summary: d.summary || '',
            shouldSpeak: shouldSpeak,
            llmPriority: d.priority || 'low',
            recentLines: d.recent_lines || [],
            lastShouldSpeak: shouldSpeak,
            lastError: '',
          });
        },
        fail: (err) => {
          console.error('status request fail', err);
          this.setError(err?.errMsg || '请求失败');
        },
      });
    };
    poll();
    this.pollTimer = setInterval(poll, POLL_INTERVAL_MS);
  },

  stopPoll() {
    if (this.pollTimer) clearInterval(this.pollTimer);
    this.pollTimer = null;
  },

  endMeeting() {
    wx.showModal({
      title: '结束会议',
      content: '确定结束并查看总结？',
      success: (res) => {
        if (!res.confirm) return;
        this.stopRecorder();
        this.stopPoll();
        wx.request({
          url: app.globalData.baseUrl + '/api/meeting/end?meeting_id=' + this.data.meetingId,
          method: 'POST',
          success: (r) => {
            const report = (r.data && r.data.final_report) ? r.data.final_report : null;
            const summary = (r.data && r.data.final_summary) ? r.data.final_summary : '';

            let content = '暂无复盘报告';
            if (report) {
              const overall = report.overall_summary || '';
              const keyPoints = Array.isArray(report.key_points) ? report.key_points : [];
              const roleInsight = report.your_role_goal_insight || '';
              const better = Array.isArray(report.better_speaking) ? report.better_speaking : [];

              const keyText = keyPoints.map(p => `- ${p}`).join('\n');
              const betterText = better
                .map((b, idx) => `${idx + 1}. 适合时机：${b.when || ''}\n建议话术：${b.what_to_say || ''}\n原因：${b.why || ''}`)
                .join('\n\n');

              content =
                `总体总结：${overall || summary || ''}\n\n` +
                `关键点：\n${keyText || '-（未识别到）'}\n\n` +
                `你的角色/目的理解：${roleInsight || ''}\n\n` +
                `更好的发言建议：\n${betterText || '-（未识别到）'}`;
            } else {
              content = summary ? `总体总结：${summary}` : '暂无复盘报告';
            }

            wx.showModal({
              title: '会议复盘',
              content: content.slice(0, 1500) + (content.length > 1500 ? '...' : ''),
              showCancel: false,
              success: () => wx.navigateBack(),
            });
          },
          fail: (err) => {
            console.error('end meeting fail', err);
            this.setError(err?.errMsg || '结束失败');
            wx.navigateBack();
          },
        });
      },
    });
  },
});
