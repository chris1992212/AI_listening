// 会议设置页：填写主题与目标，点击开始后创建会议并跳转 live
const app = getApp();

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
      if (res.statusCode !== 200 || !res.data || !res.data.meeting_id) {
        wx.showToast({ title: res.data?.detail || '创建失败', icon: 'none' });
        return;
      }
      app.globalData.meetingId = res.data.meeting_id;
      wx.navigateTo({
        url: '/pages/meeting/live?meeting_id=' + res.data.meeting_id,
      });
    } catch (e) {
      wx.hideLoading();
      wx.showToast({ title: '网络错误', icon: 'none' });
    }
  },
});
