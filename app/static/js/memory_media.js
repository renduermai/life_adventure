/* Shared cloud-image client. Imported by later item/wish forms; no automatic uploads. */
const memoryStorageStatus = fetch('/api/shining-memories/status').then(async response => {
  const status = await response.json();
  if (!response.ok) throw Error(status.error || '请先登录后使用云端图片。');
  if (!status.storage_available) throw Error(status.storage_message || '云端图片暂不可用，仍可保存不带图片的记录。');
  return status;
}).then(status => ({status}), error => ({error}));
memoryStorageStatus.then(({error}) => {
  const input = document.querySelector('#item-form input[type=file],#wish-form input[type=file]');
  if (!input) return;
  const notice = document.createElement('p'); notice.setAttribute('role','status'); notice.id='memory-storage-notice';
  notice.textContent = error ? error.message + ' 仍可保存不带图片的记录。' : '图片将保存至私有云端，仅通过已授权的后端接口读取。';
  input.closest('label').before(notice); input.setAttribute('aria-describedby',notice.id);
});
window.MemoryMedia = Object.freeze({
  async save(file, {requestId, assetId = null, version = null} = {}) {
    if (!requestId) throw Error('缺少上传编号，请重新选择图片。');
    const availability = await memoryStorageStatus;
    if (availability.error) throw availability.error;
    if (!file || !file.size || file.size > 5 * 1024 * 1024) throw Error('图片不能为空，且不得超过5MB。');
    const query = new URLSearchParams({filename: file.name, request_id: requestId});
    if (assetId) query.set('expected_version', String(version));
    const response = await fetch('/api/shining-memories/assets' + (assetId ? '/' + encodeURIComponent(assetId) : '') + '?' + query,
      {method: assetId ? 'PUT' : 'POST', headers: {'Content-Type': file.type || 'application/octet-stream'}, body: file});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || '图片上传失败，请重新读取；原图保留。');
    return data;
  },
  async remove(assetId, version) {
    const response = await fetch('/api/shining-memories/assets/' + encodeURIComponent(assetId) + '?expected_version=' + encodeURIComponent(version), {method: 'DELETE'});
    const data = await response.json();
    if (!response.ok) throw Error(data.error || '删除失败，请重试。');
    return data;
  }
});
