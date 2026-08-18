// Balance Group Messenger – small helpers

document.addEventListener('DOMContentLoaded', () => {
  // Auto-dismiss alerts after 6s
  document.querySelectorAll('.alert-dismissible').forEach(el => {
    setTimeout(() => {
      const btn = el.querySelector('.btn-close');
      if (btn) btn.click();
    }, 6000);
  });
});
