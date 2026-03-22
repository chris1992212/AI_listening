// 会议设置页：填写主题与目标，点击开始后创建会议并跳转 live
const app = getApp();
const { normalizeWxData } = require('../../utils/request.js');

Page({
  data: {
    topic: '',
    goalType: '展示能力',
    goalDesc: '',
    goalTypes: ['展示能力', '刷存在感', '推动决策', '争取资源', '澄清问题', '其他'],
  },

  onTopicInput(e) {
    this.setData({ topic: e.detail.value });
  },
  onGoalDescInput(e) {
    this.setData({ goalDesc: e.detail.value });
  },
  onGoalTypeChange(e) {
    this.setData({ goalType: this.data.goalTypes[e.detail.value] || this.data.goalTypes[0] });
  },

  async startMeeting() {
    const { topic, goalType, goalDesc } = this.data;
    if (!topic.trim()) {
      wx.showToast({ title: '请填写会议主题', icon: 'none' });
      return;
    }
    wx.showLoading({ title: '创建中...' });
    try {
      const baseUrl = app.globalData.baseUrl;
      const res = await new Promise((resolve, reject) => {
        wx.request({
          url: baseUrl + '/api/meeting/start',
          method: 'POST',
          header: { 'content-type': 'application/json' },
          data: {
            topic: topic.trim(),
            goal_type: goalType,
            goal_desc: (goalDesc || topic).trim(),
            role: '参会人',
          },
          success: resolve,
          fail: reject,
        });
      });
      wx.hideLoading();
      const data = normalizeWxData(res.data);
      if (res.statusCode !== 200 || !data || !data.meeting_id) {
        const detail = (data && data.detail) ? String(data.detail) : `HTTP ${res.statusCode}`;
        console.error('[start] fail', res.statusCode, res.data);
        wx.showToast({ title: detail.slice(0, 40) || '创建失败', icon: 'none' });
        return;
      }
      app.globalData.meetingId = data.meeting_id;
      wx.navigateTo({
        url: '/pages/meeting/live?meeting_id=' + data.meeting_id,
      });
    } catch (e) {
      wx.hideLoading();
      const msg = (e && e.errMsg) ? e.errMsg : '网络错误';
      console.error('[start] catch', e);
      wx.showToast({ title: msg.slice(0, 40), icon: 'none' });
    }
  },
});
