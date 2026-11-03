(function () {
  const doc = window.parent.document;
  if (doc.__fcPasteBound) { return; }
  doc.__fcPasteBound = true;

  function findFileInput() {
    return doc.querySelector('div[data-testid="stFileUploader"] input[type="file"]');
  }

  doc.addEventListener("paste", function (event) {
    const items = event.clipboardData && event.clipboardData.items;
    if (!items) { return; }
    for (let i = 0; i < items.length; i++) {
      const item = items[i];
      if (!item.type || item.type.indexOf("image") !== 0) { continue; }
      const blob = item.getAsFile();
      if (!blob) { continue; }
      const input = findFileInput();
      if (!input) { return; }
      const name = blob.name && blob.name !== "image.png"
        ? blob.name
        : "pasted-image.png";
      const file = new File([blob], name, { type: blob.type || "image/png" });
      const transfer = new DataTransfer();
      transfer.items.add(file);
      input.files = transfer.files;
      input.dispatchEvent(new Event("change", { bubbles: true }));
      event.preventDefault();
      break;
    }
  }, true);
})();
