(function () {
    const config = window.APP_I18N || { lang: "en", translations: {} };
    const translations = config.translations || {};

    if (config.lang !== "ru") {
        return;
    }

    function translateText(value) {
        const trimmed = value.trim();
        if (!trimmed || !translations[trimmed]) {
            return value;
        }
        return value.replace(trimmed, translations[trimmed]);
    }

    function translateElementAttributes(element) {
        ["placeholder", "title", "aria-label"].forEach(function (attribute) {
            if (!element.hasAttribute(attribute)) {
                return;
            }
            const value = element.getAttribute(attribute);
            if (translations[value]) {
                element.setAttribute(attribute, translations[value]);
            }
        });
    }

    function translateNode(node) {
        if (node.nodeType === Node.TEXT_NODE) {
            node.nodeValue = translateText(node.nodeValue);
            return;
        }

        if (node.nodeType !== Node.ELEMENT_NODE) {
            return;
        }

        if (["SCRIPT", "STYLE", "CODE", "PRE"].includes(node.tagName)) {
            return;
        }

        translateElementAttributes(node);
        node.childNodes.forEach(translateNode);
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.documentElement.lang = config.lang;
        document.title = translations[document.title] || document.title;
        translateNode(document.body);
    });
})();
