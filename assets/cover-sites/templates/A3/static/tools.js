"use strict";
(() => {
  const id = name => document.getElementById(name);
  const on = (name, handler) => { if (id(name)) id(name).addEventListener('click', handler); };
  const json = id('json-input');
  if (json) {
    function perform(compact) {
      try {
        const data = JSON.parse(json.value);
        id('json-output').value = JSON.stringify(data, null, compact ? 0 : 2);
        id('json-error').textContent = '';
      } catch (error) {
        id('json-output').value = '';
        id('json-error').textContent = 'Invalid JSON: ' + String(error.message);
      }
    }
    on('json-format', () => perform(false));
    on('json-compact', () => perform(true));
    on('json-clear', () => { json.value=''; id('json-output').value=''; id('json-error').textContent=''; });
    perform(false);
  }
  const url = id('url-input');
  if (url) {
    function transform(fn) {
      try {
        id('url-output').value = fn(url.value);
        id('url-error').textContent = '';
      } catch (error) {
        id('url-output').value='';
        id('url-error').textContent = 'Cannot process input: ' + String(error.message);
      }
    }
    on('url-encode', () => transform(encodeURIComponent));
    on('url-decode', () => transform(decodeURIComponent));
    on('url-clear', () => { url.value=''; id('url-output').value=''; id('url-error').textContent=''; });
    transform(encodeURIComponent);
  }
})();
