(function () {
    document.addEventListener("DOMContentLoaded", function () {
        const input = document.querySelector("[data-question-input]");
        if (!input) {
            return;
        }

        document.querySelectorAll("[data-question-suggestion]").forEach(function (button) {
            button.addEventListener("click", function () {
                input.value = button.getAttribute("data-question-suggestion") || "";
                input.focus();
            });
        });
    });
})();
