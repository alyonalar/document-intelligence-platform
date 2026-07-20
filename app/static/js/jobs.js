(function () {
    var i18nConfig = window.APP_I18N || { lang: "en", translations: {} };
    var translations = i18nConfig.translations || {};

    function translate(value) {
        if (i18nConfig.lang !== "ru" || !value) {
            return value;
        }
        if (translations[value]) {
            return translations[value];
        }
        if (value.indexOf("Indexed ") === 0 && value.endsWith(" semantic chunk(s).")) {
            return "Проиндексировано семантических фрагментов: " + value.replace("Indexed ", "").replace(" semantic chunk(s).", "") + ".";
        }
        if (value.indexOf("Processed and indexed ") === 0 && value.indexOf(" semantic chunk(s).") !== -1) {
            return "Обработано и проиндексировано семантических фрагментов: " + value.replace("Processed and indexed ", "").split(" semantic chunk(s).")[0] + ".";
        }
        return value;
    }

    function formatDate(value) {
        if (!value) {
            return "";
        }
        var date = new Date(value);
        if (Number.isNaN(date.getTime())) {
            return value;
        }
        return date.toLocaleString();
    }

    function renderJob(job, includeDocument) {
        var article = document.createElement("article");
        article.className = "job-item";

        var header = document.createElement("div");
        var title = document.createElement("strong");
        title.textContent = translate(job.job_type);

        var badge = document.createElement("span");
        badge.className = "status-badge status-" + job.status;
        badge.textContent = translate(job.status);

        header.appendChild(title);
        header.appendChild(badge);

        var message = document.createElement("p");
        message.className = "preview-text";
        message.textContent = translate(job.message || "No message");

        var meta = document.createElement("p");
        meta.className = "source-meta";
        var parts = [];
        if (includeDocument && job.document_id) {
            parts.push(translate("Document") + " " + job.document_id);
        }
        parts.push(translate("Created") + " " + formatDate(job.created_at));
        if (job.started_at) {
            parts.push(translate("Started") + " " + formatDate(job.started_at));
        }
        if (job.finished_at) {
            parts.push(translate("Finished") + " " + formatDate(job.finished_at));
        }
        meta.textContent = parts.join(" / ");

        article.appendChild(header);
        article.appendChild(message);
        article.appendChild(meta);
        return article;
    }

    function refreshJobs(section) {
        var url = section.dataset.jobsUrl;
        var list = section.querySelector("[data-job-list]");
        if (!url || !list) {
            return Promise.resolve(false);
        }

        return fetch(url, { headers: { Accept: "application/json" } })
            .then(function (response) {
                if (!response.ok) {
                    throw new Error("Failed to load jobs");
                }
                return response.json();
            })
            .then(function (payload) {
                list.innerHTML = "";
                var jobs = payload.jobs || [];
                var includeDocument = section.dataset.includeDocument === "true";

                jobs.forEach(function (job) {
                    list.appendChild(renderJob(job, includeDocument));
                });

                if (!jobs.length) {
                    var empty = document.createElement("p");
                    empty.className = "preview-text";
                    empty.textContent = translate("No processing jobs yet.");
                    list.appendChild(empty);
                }

                return jobs.some(function (job) {
                    return job.status === "queued" || job.status === "running";
                });
            })
            .catch(function () {
                return false;
            });
    }

    document.addEventListener("DOMContentLoaded", function () {
        document.querySelectorAll("[data-jobs-url]").forEach(function (section) {
            var hasActiveJobs = section.dataset.hasActiveJobs === "true";

            refreshJobs(section).then(function (active) {
                if (!active && !hasActiveJobs) {
                    return;
                }

                var interval = window.setInterval(function () {
                    refreshJobs(section).then(function (stillActive) {
                        if (!stillActive) {
                            window.clearInterval(interval);
                        }
                    });
                }, 3000);
            });
        });
    });
})();
