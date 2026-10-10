/* ==========================================================================
   CertFlow — Clean Client-Side Certificate Maker Logic (Single & Bulk Modes)
   ========================================================================== */

let currentMode = "single"; // 'single' | 'bulk'
let bulkRecipients = [];
let activeJobId = null;
let pollInterval = null;

document.addEventListener("DOMContentLoaded", () => {
    lucide.createIcons();
    loadSampleBulkList(10, false);
    syncPreviewFromSingle();
});

// --------------------------------------------------------------------------
// Mode Switching (Single Certificate vs Bulk Certificate Maker)
// --------------------------------------------------------------------------
function openGeneratorMode(mode) {
    switchGeneratorMode(mode);
    const el = document.getElementById("generator");
    if (el) {
        el.scrollIntoView({ behavior: "smooth" });
    }
}

function switchGeneratorMode(mode) {
    currentMode = mode;

    const btnSingle = document.getElementById("tab-btn-single");
    const btnBulk = document.getElementById("tab-btn-bulk");
    const formSingle = document.getElementById("form-single-container");
    const formBulk = document.getElementById("form-bulk-container");

    if (mode === "single") {
        btnSingle.classList.add("active");
        btnBulk.classList.remove("active");
        formSingle.classList.remove("hidden");
        formBulk.classList.add("hidden");
        syncPreviewFromSingle();
    } else {
        btnBulk.classList.add("active");
        btnSingle.classList.remove("active");
        formBulk.classList.remove("hidden");
        formSingle.classList.add("hidden");
        syncPreviewFromBulk();
    }
    lucide.createIcons();
}

// --------------------------------------------------------------------------
// Live Certificate Preview Synchronization
// --------------------------------------------------------------------------
function syncPreviewFromSingle() {
    const name = document.getElementById("single-name").value.trim() || "Peter Parker";
    const subtitle = document.getElementById("single-subtitle").value.trim() || "Autonomous Flight Systems Workshop";
    const title = document.getElementById("single-title").value.trim() || "Certificate of Excellence";
    const issuer = document.getElementById("single-issuer").value.trim() || "Aereo Academy";
    const date = document.getElementById("single-date").value.trim() || "October 10, 2026";

    updateCertificateCanvas({ name, subtitle, title, issuer, date });
}

function syncPreviewFromBulk() {
    const firstPerson = bulkRecipients[0] ? bulkRecipients[0].name : "Peter Parker";
    const subtitle = document.getElementById("bulk-subtitle").value.trim() || "Autonomous Flight Systems Workshop";
    const title = document.getElementById("bulk-title").value.trim() || "Certificate of Excellence";
    const issuer = document.getElementById("bulk-issuer").value.trim() || "Aereo Academy";
    const date = document.getElementById("bulk-date").value.trim() || "October 10, 2026";

    updateCertificateCanvas({ name: firstPerson, subtitle, title, issuer, date });
}

function updateCertificateCanvas({ name, subtitle, title, issuer, date }) {
    document.getElementById("live-name").textContent = name;
    document.getElementById("live-subtitle").textContent = `for successfully completing ${subtitle}`;
    document.getElementById("live-title").textContent = title;
    document.getElementById("live-issuer").textContent = issuer.toUpperCase();
    document.getElementById("live-date").textContent = date;
}

// --------------------------------------------------------------------------
// Mode 1: Create Single Certificate
// --------------------------------------------------------------------------
async function createSingleCertificate() {
    const name = document.getElementById("single-name").value.trim();
    const email = document.getElementById("single-email").value.trim() || "awardee@example.com";
    const title = document.getElementById("single-title").value.trim();
    const eventName = document.getElementById("single-subtitle").value.trim();
    const issuer = document.getElementById("single-issuer").value.trim();
    const issueDate = document.getElementById("single-date").value.trim();

    if (!name || !eventName || !title || !issuer || !issueDate) {
        showToast("Please fill in the Name, Subtitle, and Date fields.", "warning");
        return;
    }

    const btn = document.getElementById("btn-create-single");
    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-5 h-5 animate-spin"></i><span>Creating PDF...</span>`;
    lucide.createIcons();

    await submitJobToBackend({
        title,
        eventName,
        issuer,
        issueDate,
        recipientsList: [{ name, email }],
        isSingle: true,
    });

    btn.disabled = false;
    btn.innerHTML = origHtml;
    lucide.createIcons();
}

// --------------------------------------------------------------------------
// Mode 2: Bulk Recipients Management & CSV Upload
// --------------------------------------------------------------------------
function loadSampleBulkList(count = 10, notify = true) {
    if (count === 10) {
        bulkRecipients = [
            { name: "Peter Parker", email: "peter.parker@aereo.io" },
            { name: "Roxanne Miller", email: "roxanne.miller@aereo.io" },
            { name: "Osmond Pillard", email: "osmond.pillard@aereo.io" },
            { name: "Aarav Mehta", email: "aarav.mehta@aereo.io" },
            { name: "Priya Nair", email: "priya.nair@aereo.io" },
            { name: "Rohan Verma", email: "rohan.verma@aereo.io" },
            { name: "Ananya Iyer", email: "ananya.iyer@aereo.io" },
            { name: "Vikramaditya Rao", email: "vikram.rao@aereo.io" },
            { name: "Sneha Kulkarni", email: "sneha.kulkarni@aereo.io" },
            { name: "Meera Krishnan", email: "meera.krishnan@aereo.io" },
        ];
    } else {
        bulkRecipients = [];
        for (let i = 1; i <= count; i++) {
            bulkRecipients.push({
                name: `Participant #${String(i).padStart(2, "0")}`,
                email: `participant.${i}@example.com`,
            });
        }
    }

    renderBulkRecipientsTable();
    if (currentMode === "bulk") syncPreviewFromBulk();
    if (notify) showToast(`Loaded ${bulkRecipients.length} recipients.`, "success");
}

function addBulkRecipientRow() {
    const nameEl = document.getElementById("bulk-add-name");
    const emailEl = document.getElementById("bulk-add-email");
    const name = nameEl.value.trim();
    const email = emailEl.value.trim();

    if (!name || !email) {
        showToast("Please enter both Awardee Name and Email Address.", "warning");
        return;
    }

    bulkRecipients.unshift({ name, email });
    nameEl.value = "";
    emailEl.value = "";
    nameEl.focus();

    renderBulkRecipientsTable();
    syncPreviewFromBulk();
}

function removeBulkRecipientRow(idx) {
    bulkRecipients.splice(idx, 1);
    renderBulkRecipientsTable();
    syncPreviewFromBulk();
}

const EMAIL_REGEX = /^[^@\s]+@[^@\s]+\.[^@\s]+$/;

function isValidEmail(email) {
    return EMAIL_REGEX.test(String(email || "").trim());
}

function downloadSampleCsvTemplate(event) {
    if (event) {
        event.preventDefault();
        event.stopPropagation();
    }
    const sampleCsv = [
        "Name,Email",
        "Peter Parker,peter.parker@aereo.io",
        "Roxanne Miller,roxanne.miller@aereo.io",
        "Osmond Pillard,osmond.pillard@aereo.io",
        "Aarav Mehta,aarav.mehta@aereo.io",
        "Priya Nair,priya.nair@aereo.io",
    ].join("\n");

    const blob = new Blob([sampleCsv], { type: "text/csv;charset=utf-8;" });
    const url = URL.createObjectURL(blob);
    const a = document.createElement("a");
    a.href = url;
    a.download = "sample_recipients.csv";
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
    showToast("Downloaded sample_recipients.csv template!", "success");
}

function clearBulkRecipients() {
    bulkRecipients = [];
    renderBulkRecipientsTable();
}

function removeInvalidBulkRows() {
    const before = bulkRecipients.length;
    bulkRecipients = bulkRecipients.filter((r) => isValidEmail(r.email));
    const removed = before - bulkRecipients.length;
    renderBulkRecipientsTable();
    syncPreviewFromBulk();
    showToast(`Removed ${removed} invalid row(s).`, "info");
}

function uploadBulkCsv(event) {
    const file = event.target.files[0];
    if (!file) return;

    const reader = new FileReader();
    reader.onload = (e) => {
        const text = e.target.result || "";
        const lines = text.split(/\r?\n/).map((l) => l.trim()).filter(Boolean);
        const imported = [];

        for (let i = 0; i < lines.length; i++) {
            const parts = lines[i].split(",").map((p) => p.trim().replace(/^["']|["']$/g, ""));
            if (parts.length < 2) continue;
            // Skip header row only if it explicitly says Name, Email
            if (i === 0 && parts[0].toLowerCase() === "name" && parts[1].toLowerCase().includes("email")) {
                continue;
            }
            if (parts[0] && parts[1]) {
                imported.push({ name: parts[0], email: parts[1] });
            }
        }

        // Reset file input so same file can be re-selected if needed
        event.target.value = "";

        if (imported.length === 0) {
            showToast("Invalid CSV: File must contain 2 columns (Name, Email).", "error");
            return;
        }

        bulkRecipients = imported;
        renderBulkRecipientsTable();
        syncPreviewFromBulk();

        const invalidCount = imported.filter((r) => !isValidEmail(r.email)).length;
        if (invalidCount === imported.length) {
            showToast(
                `Invalid CSV Uploaded! All ${invalidCount} rows are missing valid emails (Expected: Name, Email).`,
                "error"
            );
        } else if (invalidCount > 0) {
            showToast(
                `CSV Uploaded with ${invalidCount} invalid row(s) marked INVALID.`,
                "warning"
            );
        } else {
            showToast(`Uploaded ${imported.length} valid recipients from CSV!`, "success");
        }
    };
    reader.readAsText(file);
}

function renderBulkRecipientsTable() {
    const tbody = document.getElementById("bulk-recipients-tbody");
    const countLabel = document.getElementById("bulk-count-label");
    const invalidBanner = document.getElementById("csv-invalid-banner");
    const invalidTitle = document.getElementById("csv-invalid-title");
    const invalidDesc = document.getElementById("csv-invalid-desc");
    const uploadBtn = document.getElementById("upload-csv-btn");

    countLabel.textContent = bulkRecipients.length;

    const invalidCount = bulkRecipients.filter((r) => !isValidEmail(r.email)).length;

    if (invalidBanner) {
        if (invalidCount > 0) {
            invalidBanner.classList.remove("hidden");
            if (invalidCount === bulkRecipients.length) {
                invalidTitle.textContent = `Invalid CSV Format — All ${invalidCount} Rows Are Invalid`;
                invalidDesc.innerHTML = `None of the rows contain a valid email address. Expected 2 columns: <strong>Name, Email</strong> (e.g. <code>Peter Parker, peter@example.com</code>).`;
            } else {
                invalidTitle.textContent = `${invalidCount} Invalid Row(s) Detected`;
                invalidDesc.innerHTML = `${invalidCount} of ${bulkRecipients.length} rows do not have a valid email address and are marked <strong>INVALID</strong> below.`;
            }
            if (uploadBtn) {
                uploadBtn.className = "px-3.5 py-2 rounded-lg bg-red-600 hover:bg-red-700 text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer transition ring-2 ring-red-300";
            }
        } else {
            invalidBanner.classList.add("hidden");
            if (uploadBtn) {
                uploadBtn.className = "px-3.5 py-2 rounded-lg bg-gray-900 hover:bg-gray-800 text-white text-xs font-bold flex items-center gap-1.5 cursor-pointer transition";
            }
        }
    }

    if (bulkRecipients.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="5" class="py-8 text-center text-gray-400 text-sm">
                    No recipients added yet. Add someone above or click <strong>"Load 10 Sample Recipients"</strong>.
                </td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = bulkRecipients
        .map((r, idx) => {
            const valid = isValidEmail(r.email);
            const rowClass = valid ? "hover:bg-gray-50" : "bg-red-50/70 hover:bg-red-50";
            const statusBadge = valid
                ? `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">✓ Valid</span>`
                : `<span class="inline-flex items-center gap-1 px-2.5 py-0.5 rounded-full text-xs font-bold bg-red-100 text-red-700 border border-red-300">✕ Invalid</span>`;

            return `
            <tr class="${rowClass} transition">
                <td class="py-2.5 px-4 text-gray-400 font-semibold">${idx + 1}</td>
                <td class="py-2.5 px-4 font-bold ${valid ? "text-gray-900" : "text-red-900"}">${escapeHtml(r.name)}</td>
                <td class="py-2.5 px-4 ${valid ? "text-gray-600" : "text-red-600 font-medium line-through"}">${escapeHtml(r.email)}</td>
                <td class="py-2.5 px-4">${statusBadge}</td>
                <td class="py-2.5 px-4 text-right">
                    <button
                        type="button"
                        onclick="removeBulkRecipientRow(${idx})"
                        class="text-gray-400 hover:text-red-600 p-1 transition"
                        title="Remove"
                    >
                        <i data-lucide="trash-2" class="w-4 h-4"></i>
                    </button>
                </td>
            </tr>
        `;
        })
        .join("");

    lucide.createIcons();
}

async function createBulkCertificates() {
    if (bulkRecipients.length === 0) {
        showToast("Please add at least 1 recipient to the list.", "warning");
        return;
    }

    const title = document.getElementById("bulk-title").value.trim();
    const eventName = document.getElementById("bulk-subtitle").value.trim();
    const issuer = document.getElementById("bulk-issuer").value.trim();
    const issueDate = document.getElementById("bulk-date").value.trim();

    if (!title || !eventName || !issuer || !issueDate) {
        showToast("Please complete all certificate details.", "warning");
        return;
    }

    const btn = document.getElementById("btn-create-bulk");
    const origHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = `<i data-lucide="loader-2" class="w-5 h-5 animate-spin"></i><span>Generating Batch...</span>`;
    lucide.createIcons();

    await submitJobToBackend({
        title,
        eventName,
        issuer,
        issueDate,
        recipientsList: bulkRecipients,
        isSingle: false,
    });

    btn.disabled = false;
    btn.innerHTML = origHtml;
    lucide.createIcons();
}

// --------------------------------------------------------------------------
// Shared Backend Job Submission & Real-Time Download Section
// --------------------------------------------------------------------------
async function submitJobToBackend({ title, eventName, issuer, issueDate, recipientsList, isSingle }) {
    try {
        const res = await fetch("/v1/jobs", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify({
                certificate_info: {
                    title,
                    event_name: eventName,
                    issuer,
                    issue_date: issueDate,
                },
                recipients: recipientsList,
            }),
        });

        const data = await res.json();
        if (!res.ok) {
            const msg = typeof data.detail === "string" ? data.detail : "Invalid input data.";
            showToast(msg, "error");
            return;
        }

        activeJobId = data.job_id;

        // Reveal the Results & Downloads card and scroll smoothly to it
        const resultsSection = document.getElementById("results-section");
        resultsSection.classList.remove("hidden");
        resultsSection.scrollIntoView({ behavior: "smooth", block: "nearest" });

        startPollingResults(isSingle);
    } catch (err) {
        showToast(`Could not connect to server: ${err.message}`, "error");
    }
}

function startPollingResults(isSingle) {
    if (pollInterval) clearInterval(pollInterval);
    pollJobStatus(isSingle);
    pollInterval = setInterval(() => pollJobStatus(isSingle), 700);
}

async function pollJobStatus(isSingle) {
    if (!activeJobId) return;

    try {
        const [jobRes, certsRes] = await Promise.all([
            fetch(`/v1/jobs/${activeJobId}`),
            fetch(`/v1/jobs/${activeJobId}/certificates?page=1&page_size=100`),
        ]);

        if (!jobRes.ok) return;

        const job = await jobRes.json();
        const certsData = certsRes.ok ? await certsRes.json() : { items: [] };
        const items = certsData.items || [];

        const p = job.progress;
        const pct = p.percent_complete || 0;

        document.getElementById("progress-bar-fill").style.width = `${pct}%`;
        document.getElementById("progress-percent-text").textContent = `${pct}%`;

        const pill = document.getElementById("result-status-pill");
        const statusText = document.getElementById("progress-status-text");
        const zipBtn = document.getElementById("btn-download-all-zip");

        zipBtn.disabled = p.succeeded === 0;

        const isDone = job.status !== "queued" && job.status !== "processing";
        if (isDone) {
            clearInterval(pollInterval);
            pollInterval = null;
            pill.textContent = "Ready to Download";
            pill.className = "px-3 py-1 rounded-full text-xs font-bold uppercase bg-emerald-100 text-emerald-800";
            statusText.textContent = `Completed: ${p.succeeded} certificate(s) ready for download`;
            showToast("Your certificate PDF is ready to download!", "success");
        } else {
            pill.textContent = "Generating PDF...";
            pill.className = "px-3 py-1 rounded-full text-xs font-bold uppercase bg-amber-100 text-amber-800";
            statusText.textContent = `Rendering ${p.succeeded} of ${p.total} certificates...`;
        }

        renderGeneratedCertificatesRows(items);
    } catch (err) {
        console.error(err);
    }
}

function renderGeneratedCertificatesRows(items) {
    const tbody = document.getElementById("generated-certs-tbody");

    if (items.length === 0) {
        tbody.innerHTML = `
            <tr>
                <td colspan="4" class="py-6 text-center text-gray-400">Preparing certificates...</td>
            </tr>
        `;
        return;
    }

    tbody.innerHTML = items
        .map((c) => {
            const isReady = c.status === "succeeded";
            const isError = c.status === "rejected" || c.status === "failed";

            const statusBadge = isReady
                ? `<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-emerald-100 text-emerald-800">Ready</span>`
                : isError
                ? `<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-red-100 text-red-700">${escapeHtml(
                      c.error_message || "Invalid Email"
                  )}</span>`
                : `<span class="px-2.5 py-1 rounded-full text-xs font-bold bg-amber-100 text-amber-800">Generating...</span>`;

            const downloadBtn = isReady
                ? `
                <div class="flex items-center justify-end gap-2">
                    <a
                        href="/v1/certificates/${c.id}/download"
                        class="px-4 py-2 rounded-lg bg-emerald-600 hover:bg-emerald-700 text-white text-xs font-bold inline-flex items-center gap-1.5 shadow-sm transition"
                    >
                        <i data-lucide="download" class="w-3.5 h-3.5"></i>
                        <span>Download PDF</span>
                    </a>
                    <a
                        href="/verify/${c.verification_code}"
                        target="_blank"
                        class="px-3 py-2 rounded-lg bg-gray-100 hover:bg-gray-200 text-gray-700 text-xs font-bold inline-flex items-center gap-1 transition"
                        title="View Verification Badge"
                    >
                        <i data-lucide="shield-check" class="w-3.5 h-3.5 text-emerald-600"></i>
                        <span>Verify</span>
                    </a>
                </div>
            `
                : `<span class="text-xs text-gray-400">—</span>`;

            return `
                <tr class="hover:bg-gray-50 transition">
                    <td class="py-3.5 px-4">
                        <div class="font-bold text-gray-900">${escapeHtml(c.recipient_name)}</div>
                        <div class="text-xs text-gray-500">${escapeHtml(c.recipient_email)}</div>
                    </td>
                    <td class="py-3.5 px-4">${statusBadge}</td>
                    <td class="py-3.5 px-4 font-mono text-xs text-gray-600">${escapeHtml(c.verification_code)}</td>
                    <td class="py-3.5 px-4 text-right">${downloadBtn}</td>
                </tr>
            `;
        })
        .join("");

    lucide.createIcons();
}

function downloadCurrentBatchZip() {
    if (!activeJobId) return;
    window.location.href = `/v1/jobs/${activeJobId}/download`;
}

// --------------------------------------------------------------------------
// Verify Certificate Lookup
// --------------------------------------------------------------------------
async function verifyCertificateCode() {
    const code = document.getElementById("verify-code-input").value.trim();
    if (!code) {
        showToast("Please enter a Certificate ID to verify.", "warning");
        return;
    }

    const box = document.getElementById("verify-output-box");
    box.classList.remove("hidden");
    box.innerHTML = `<div class="p-4 rounded-xl bg-gray-50 text-center text-sm text-gray-500">Checking certificate...</div>`;

    try {
        const res = await fetch(`/verify/${encodeURIComponent(code)}`, {
            headers: { Accept: "application/json" },
        });
        const data = await res.json();

        if (res.ok && data.valid) {
            box.innerHTML = `
                <div class="p-6 rounded-2xl bg-emerald-50 border-2 border-emerald-500 space-y-3">
                    <div class="flex items-center justify-between">
                        <span class="px-3 py-1 rounded-full bg-emerald-600 text-white text-xs font-bold uppercase">
                            ✓ Verified Authentic Certificate
                        </span>
                        <a href="/verify/${encodeURIComponent(data.verification_code)}" target="_blank" class="text-xs font-bold text-emerald-700 underline">
                            Open Official Badge ↗
                        </a>
                    </div>
                    <div class="pt-1">
                        <div class="text-xl font-extrabold text-gray-900">${escapeHtml(data.recipient_name)}</div>
                        <div class="text-sm text-gray-700 font-medium">${escapeHtml(data.event_name)}</div>
                    </div>
                    <div class="text-xs text-gray-500 pt-2 border-t border-emerald-200 flex justify-between">
                        <span>Issued by: <strong>${escapeHtml(data.issuer)}</strong></span>
                        <span>Date: <strong>${escapeHtml(data.issue_date)}</strong></span>
                    </div>
                </div>
            `;
        } else {
            box.innerHTML = `
                <div class="p-6 rounded-2xl bg-red-50 border-2 border-red-300 text-center space-y-1">
                    <div class="font-bold text-red-700">Certificate Not Found</div>
                    <div class="text-xs text-red-600">No valid certificate matches ID "${escapeHtml(code)}".</div>
                </div>
            `;
        }
    } catch (err) {
        showToast("Could not verify certificate right now.", "error");
    }
}

// --------------------------------------------------------------------------
// Utilities
// --------------------------------------------------------------------------
function escapeHtml(str) {
    return String(str ?? "")
        .replace(/&/g, "&amp;")
        .replace(/</g, "&lt;")
        .replace(/>/g, "&gt;")
        .replace(/"/g, "&quot;")
        .replace(/'/g, "&#039;");
}

function showToast(message, type = "info") {
    const container = document.getElementById("toast-container");
    const el = document.createElement("div");

    const colors = {
        success: "bg-emerald-50 text-emerald-950 border-gray-900",
        error: "bg-red-50 text-red-900 border-red-600",
        warning: "bg-amber-50 text-amber-950 border-gray-900",
        info: "bg-white text-gray-900 border-gray-900",
    };

    el.className = `toast-item pointer-events-auto p-4 rounded-xl border-2 shadow-[0_4px_0_#111827] text-sm font-bold flex items-center justify-between gap-3 ${
        colors[type] || colors.info
    }`;
    el.innerHTML = `
        <span>${escapeHtml(message)}</span>
        <button onclick="this.parentElement.remove()" class="text-gray-500 hover:text-gray-900">✕</button>
    `;

    container.appendChild(el);
    setTimeout(() => {
        if (el.parentElement) el.remove();
    }, 4000);
}

