// 会议助手小程序
App({
  globalData: {
    //baseUrl: 'http://8.162.10.206:8000', // 本地调试改为你的电脑 IP，真机需 HTTPS 或内网穿透
    baseUrl: 'https://llm-listen.vip.cpolar.cn',
    meetingId: null,
  },
  onLaunch() {
    const u = this.globalData.baseUrl;
    console.log('[app] baseUrl =', u, '（真机预览请勾选「不校验合法域名」；仅支持 http 时勿用 https）');
  },
});
