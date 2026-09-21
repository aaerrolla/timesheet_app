(function () {
  "use strict";
  const $ = (s) => document.querySelector(s);
  const banner = $("#banner");

  function showBanner(message, type) {
    banner.textContent = message;
    banner.className = "banner " + type;
    banner.classList.remove("hidden");
    clearTimeout(showBanner._t);
    showBanner._t = setTimeout(() => banner.classList.add("hidden"), 5000);
  }

  async function loadProfile() {
    const res = await fetch("/api/auth/me");
    if (res.status === 401) {
      window.location.href = "/login";
      return;
    }
    const user = await res.json();
    $("#emailDisplay").textContent = `Login email: ${user.email}`;
    $("#firstName").value = user.first_name || "";
    $("#lastName").value = user.last_name || "";
    $("#mobilePhone").value = user.mobile_phone || "";
    $("#entityName").value = user.entity_name || "";
  }

  $("#profileForm").addEventListener("submit", async (e) => {
    e.preventDefault();
    try {
      const res = await fetch("/api/profile", {
        method: "PUT",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({
          first_name: $("#firstName").value.trim(),
          last_name: $("#lastName").value.trim(),
          mobile_phone: $("#mobilePhone").value.trim(),
          entity_name: $("#entityName").value.trim(),
        }),
      });
      const data = await res.json();
      if (!res.ok) {
        showBanner(data.error || "Could not save profile.", "error");
        return;
      }
      showBanner("Profile saved.", "success");
    } catch (err) {
      showBanner("Network error while saving profile.", "error");
    }
  });

  $("#passwordForm").addEventListener("submit", async (e) => {
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
      showBanner("Password updated.", "success");
      $("#passwordForm").reset();
    } catch (err) {
      showBanner("Network error while changing password.", "error");
    }
  });

  $("#logoutBtn").addEventListener("click", async () => {
    try {
      await fetch("/api/auth/logout", { method: "POST" });
    } finally {
      window.location.href = "/login";
    }
  });

  loadProfile();
})();
