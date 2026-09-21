"use strict";
(function () {
  const focus = document.querySelector("[data-violation-focus]");
  if (!focus) return;
  const control = focus.querySelector("[data-report-violations-only]");
  const report = focus.closest(".report-shell");

  control.addEventListener("change", () => {
    report.classList.toggle("violations-only", control.checked);
    const flowControl = report.querySelector(".flow-violations-only");
    if (flowControl && flowControl.checked !== control.checked) {
      flowControl.checked = control.checked;
      flowControl.dispatchEvent(new Event("change"));
    }
  });
  focus.hidden = false;
})();
