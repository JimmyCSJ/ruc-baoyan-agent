(function initAuthPage() {
  const params = new URLSearchParams(window.location.search);
  const next = params.get("next") || "/app";

  verifyAuthSession().then((ok) => {
    if (ok) window.location.replace(next.startsWith("/") ? next : "/app");
  });

  const tabLogin = document.getElementById("tabLogin");
  const tabRegister = document.getElementById("tabRegister");
  const loginForm = document.getElementById("loginForm");
  const registerForm = document.getElementById("registerForm");
  const loginErr = document.getElementById("loginErr");
  const registerErr = document.getElementById("registerErr");

  function showErr(el, msg) {
    if (!el) return;
    if (!msg) {
      el.classList.add("hidden");
      el.textContent = "";
      return;
    }
    el.textContent = msg;
    el.classList.remove("hidden");
  }

  function setTab(mode) {
    const isLogin = mode === "login";
    tabLogin?.classList.toggle("active", isLogin);
    tabRegister?.classList.toggle("active", !isLogin);
    loginForm?.classList.toggle("hidden", !isLogin);
    registerForm?.classList.toggle("hidden", isLogin);
    showErr(loginErr, "");
    showErr(registerErr, "");
  }

  tabLogin?.addEventListener("click", () => setTab("login"));
  tabRegister?.addEventListener("click", () => setTab("register"));

  async function handleAuthResponse(res) {
    const data = await res.json().catch(() => ({}));
    if (!res.ok) {
      const detail = data.detail;
      const msg = typeof detail === "string" ? detail : Array.isArray(detail) ? detail.map((x) => x.msg || x).join("；") : "请求失败";
      throw new Error(msg);
    }
    setAuthSession(data.token, data.username);
    window.location.replace(next.startsWith("/") ? next : "/app");
  }

  loginForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showErr(loginErr, "");
    const username = document.getElementById("loginUsername")?.value?.trim() || "";
    const password = document.getElementById("loginPassword")?.value || "";
    try {
      const res = await fetch("/api/auth/login", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      await handleAuthResponse(res);
    } catch (err) {
      showErr(loginErr, err.message || String(err));
    }
  });

  registerForm?.addEventListener("submit", async (e) => {
    e.preventDefault();
    showErr(registerErr, "");
    const username = document.getElementById("regUsername")?.value?.trim() || "";
    const password = document.getElementById("regPassword")?.value || "";
    const password2 = document.getElementById("regPassword2")?.value || "";
    if (password !== password2) {
      showErr(registerErr, "两次输入的密码不一致");
      return;
    }
    try {
      const res = await fetch("/api/auth/register", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ username, password }),
      });
      await handleAuthResponse(res);
    } catch (err) {
      showErr(registerErr, err.message || String(err));
    }
  });
})();
