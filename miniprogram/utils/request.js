/**
 * 微信 wx.request / uploadFile 的 success 里，部分环境下 res.data 可能是字符串，需手动 JSON.parse。
 * @param {*} data res.data
 * @returns {object|null}
 */
function normalizeWxData(data) {
  if (data == null || data === '') return null;
  if (typeof data === 'object' && !Array.isArray(data)) return data;
  if (typeof data === 'string') {
    try {
      return JSON.parse(data);
    } catch (e) {
      return { _parseError: true, _raw: data };
    }
  }
  return data;
}

module.exports = {
  normalizeWxData,
};
