(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const banner = $("#banner");

  function showBanner(message, type) {
    banner.textContent = message;
    banner.className = "banner " + type;
    banner.classList.remove("hidden");
  }

  $("#changePasswordForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    const current_password = $("#currentPassword").value;
    const new_password = $("#newPassword").value;
    const confirm_password = $("#confirmPassword").value;

    if (new_password !== confirm_password) {
      showBanner("New password and confirmation do not match.", "error");
      return;
    }

    try {
      const res = await fetch("/api/auth/change-password", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ current_password, new_password }),
      });
      const data = await res.json();
      if (!res.ok) {
        showBanner(data.error || "Could not change password.", "error");
        return;
      }
      window.location.href = "/";
    } catch (err) {
      showBanner("Network error while changing your password.", "error");
    }
  });

  $("#logoutLink").addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.href = "/login";
    }
  });
})();
