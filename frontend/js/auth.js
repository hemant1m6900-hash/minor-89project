/**
 * Authentication helper & Login/Register controller.
 */
(function (global) {
  async function requireAuth() {
    const token = global.API.getToken();
    if (!token) {
      window.location.href = '/frontend/index.html';
      return null;
    }
    try {
      const user = await global.API.get('/api/auth/me');
      global.API.setSession(token, user);
      return user;
    } catch (err) {
      if (err.status === 401) {
        global.API.clearSession();
        window.location.href = '/frontend/index.html';
        return null;
      }
      return global.API.getStoredUser();
    }
  }

  function logout() {
    global.API.clearSession();
    window.location.href = '/frontend/index.html';
  }

  function initLoginPage() {
    const loginForm = document.getElementById('login-form');
    const registerForm = document.getElementById('register-form');
    const tabLogin = document.getElementById('tab-login');
    const tabRegister = document.getElementById('tab-register');
    const authError = document.getElementById('auth-error');
    const apiBaseInput = document.getElementById('login-api-base');
    const backendStatusHint = document.getElementById('backend-status-hint');

    if (!loginForm) return;

    function syncApiBaseFromInput() {
      if (!apiBaseInput) return;
      const val = apiBaseInput.value.trim();
      if (!val || val === window.location.origin) {
        global.API.setApiBase('');
      } else {
        global.API.setApiBase(val);
      }
    }

    async function checkBackendHealth() {
      if (!backendStatusHint) return;
      const target = global.API.getApiBase() || window.location.origin;
      backendStatusHint.textContent = `Checking FastAPI backend at ${target}...`;
      backendStatusHint.style.color = 'var(--navy-52)';
      try {
        const res = await global.API.get('/api/health');
        if (res && res.status === 'ok') {
          backendStatusHint.textContent = `Connected to FastAPI backend (${target}) · SQLite ${res.database_connected ? 'ready' : 'unavailable'}.`;
          backendStatusHint.style.color = 'var(--navy)';
        } else {
          backendStatusHint.textContent = `Unexpected response from ${target}/api/health.`;
          backendStatusHint.style.color = 'var(--pink)';
        }
      } catch (err) {
        backendStatusHint.textContent =
          err.status === 404
            ? `No FastAPI backend at ${target} (404). Open the app from http://127.0.0.1:8000 after running uvicorn.`
            : err.message;
        backendStatusHint.style.color = 'var(--pink)';
      }
    }

    if (global.API.getToken()) {
      global.API.get('/api/auth/me')
        .then(() => {
          window.location.href = '/frontend/dashboard.html';
        })
        .catch(() => {
          global.API.clearSession();
        });
    }

    if (apiBaseInput) {
      apiBaseInput.value = global.API.getApiBase() || window.location.origin;
      apiBaseInput.addEventListener('change', () => {
        syncApiBaseFromInput();
        checkBackendHealth();
      });
    }

    checkBackendHealth();

    function showError(msg) {
      authError.textContent = msg;
      authError.style.display = 'block';
    }

    function clearError() {
      authError.textContent = '';
      authError.style.display = 'none';
    }

    tabLogin.addEventListener('click', () => {
      clearError();
      tabLogin.classList.add('active');
      tabRegister.classList.remove('active');
      loginForm.style.display = 'flex';
      registerForm.style.display = 'none';
    });

    tabRegister.addEventListener('click', () => {
      clearError();
      tabRegister.classList.add('active');
      tabLogin.classList.remove('active');
      registerForm.style.display = 'flex';
      loginForm.style.display = 'none';
    });

    loginForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearError();
      syncApiBaseFromInput();
      const btn = loginForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      btn.textContent = 'Signing in...';
      try {
        const email = document.getElementById('login-email').value.trim();
        const password = document.getElementById('login-password').value;
        const data = await global.API.post('/api/auth/login', { email, password });
        global.API.setSession(data.access_token, data.user);
        window.location.href = '/frontend/dashboard.html';
      } catch (err) {
        showError(err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Sign In';
      }
    });

    registerForm.addEventListener('submit', async (e) => {
      e.preventDefault();
      clearError();
      syncApiBaseFromInput();
      const btn = registerForm.querySelector('button[type="submit"]');
      btn.disabled = true;
      btn.textContent = 'Creating account...';
      try {
        const full_name = document.getElementById('reg-name').value.trim();
        const email = document.getElementById('reg-email').value.trim();
        const password = document.getElementById('reg-password').value;
        const data = await global.API.post('/api/auth/register', { full_name, email, password });
        global.API.setSession(data.access_token, data.user);
        window.location.href = '/frontend/dashboard.html';
      } catch (err) {
        showError(err.message);
      } finally {
        btn.disabled = false;
        btn.textContent = 'Create Account';
      }
    });
  }

  document.addEventListener('DOMContentLoaded', initLoginPage);

  global.Auth = {
    requireAuth,
    logout,
  };
})(window);
