'use strict';
const copyButton = document.querySelector('#copy-command');
if (navigator.clipboard && window.isSecureContext) {
  copyButton.hidden = false;
  copyButton.addEventListener('click', async () => {
    try {
      await navigator.clipboard.writeText(document.querySelector('#quickstart-code').textContent);
      copyButton.textContent = 'Copied';
      document.querySelector('#copy-status').textContent = 'Commands copied to clipboard.';
    } catch {
      copyButton.textContent = 'Select commands to copy';
      document.querySelector('#copy-status').textContent = 'Clipboard unavailable. Select the command text and copy it.';
    }
  });
}
