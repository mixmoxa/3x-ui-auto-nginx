"use strict";
(() => {
  const form = document.getElementById('budget-form');
  if (!form) return;
  const get = id => document.getElementById(id);
  const fmt = num => new Intl.NumberFormat('en-US').format(num);
  function calculate(ev) {
    if (ev) ev.preventDefault();
    const total = Number(get('requests').value);
    const failed = Number(get('failed').value);
    const target = Number(get('objective').value);
    const valid = Number.isSafeInteger(total) && total > 0 && total <= 1e9 &&
      Number.isSafeInteger(failed) && failed >= 0 && failed <= total &&
      Number.isFinite(target) && target >= 1 && target <= 100;
    if (!valid) {
      get('budget-error').textContent = 'Enter positive whole request counts, failures no greater than requests, and a target between 1 and 100%.';
      for (const id of ['observed','allowed','remaining']) get(id).textContent='—';
      return;
    }
    get('budget-error').textContent = '';
    const allowed = Math.floor(total * (1 - target / 100) + 1e-9);
    get('observed').textContent = ((total-failed)/total*100).toFixed(3) + '%';
    get('allowed').textContent = fmt(allowed);
    get('remaining').textContent = (allowed-failed >= 0 ? '' : '−') + fmt(Math.abs(allowed-failed));
  }
  form.addEventListener('submit', calculate);
  calculate();
})();
