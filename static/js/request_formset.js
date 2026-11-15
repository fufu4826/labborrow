(function () {
  var container = document.getElementById("item-rows");
  if (!container) return;
  var total = document.getElementById("id_form-TOTAL_FORMS");
  var tpl = document.getElementById("empty-form");

  function reindex() {
    var rows = container.querySelectorAll(".item-row");
    rows.forEach(function (row, idx) {
      row.querySelectorAll("select, input").forEach(function (el) {
        el.name = el.name.replace(/form-\d+-/, "form-" + idx + "-");
        el.id = el.id.replace(/form-\d+-/, "form-" + idx + "-");
      });
    });
    total.value = rows.length;
  }

  document.getElementById("add-row").addEventListener("click", function () {
    var index = parseInt(total.value, 10);
    var wrapper = document.createElement("div");
    wrapper.innerHTML = tpl.innerHTML.replace(/__prefix__/g, index).trim();
    container.appendChild(wrapper.firstElementChild);
    total.value = index + 1;
  });

  container.addEventListener("click", function (e) {
    var btn = e.target.closest(".remove-row");
    if (!btn) return;
    var row = btn.closest(".item-row");
    if (container.querySelectorAll(".item-row").length <= 1) {
      row.querySelectorAll("select").forEach(function (s) { s.value = ""; });
      return;
    }
    row.remove();
    reindex();
  });
})();
