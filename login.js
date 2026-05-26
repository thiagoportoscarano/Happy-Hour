// ============================================================
//  login.js — CORRIGIDO
//  Bugs resolvidos:
//  1. Login agora salva: usuarioLogado, usuarioId, usuarioTipo, usuarioEmail
//  2. Redirecionamento correto: organizador → painel_organizador | cliente → index
//  3. Função doForgot corrigida (não usava loading state corretamente)
// ============================================================

function switchTab(tab) {
  const isLogin = tab === 'login';
  document.getElementById('tabLogin').classList.toggle('active', isLogin);
  document.getElementById('tabRegister').classList.toggle('active', !isLogin);
  document.getElementById('loginForm').style.display    = isLogin ? 'block' : 'none';
  document.getElementById('registerForm').style.display = !isLogin ? 'block' : 'none';
  document.getElementById('successBox').classList.remove('show');
  document.getElementById('forgotForm').style.display   = 'none';
  document.querySelector('.left-content h2').innerHTML =
    isLogin ? 'Bem-vindo<br>de <em>volta.</em>' : 'Sua noite<br><em>começa aqui.</em>';
}

function showForgot() {
  document.getElementById('loginForm').style.display  = 'none';
  document.getElementById('forgotForm').style.display = 'block';
}

function togglePwd(id, btn) {
  const inp = document.getElementById(id);
  const show = inp.type === 'password';
  inp.type = show ? 'text' : 'password';
  btn.innerHTML = show
    ? `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M17.94 17.94A10.07 10.07 0 0 1 12 20c-7 0-11-8-11-8a18.45 18.45 0 0 1 5.06-5.94"/><path d="M9.9 4.24A9.12 9.12 0 0 1 12 4c7 0 11 8 11 8a18.5 18.5 0 0 1-2.16 3.19"/><line x1="1" y1="1" x2="23" y2="23"/></svg>`
    : `<svg width="16" height="16" fill="none" stroke="currentColor" stroke-width="2" viewBox="0 0 24 24"><path d="M1 12s4-8 11-8 11 8 11 8-4 8-11 8-11-8-11-8z"/><circle cx="12" cy="12" r="3"/></svg>`;
}

function maskCpf(inp) {
  let v = inp.value.replace(/\D/g, '').slice(0, 11);
  if (v.length > 9)      v = v.replace(/(\d{3})(\d{3})(\d{3})(\d{0,2})/, '$1.$2.$3-$4');
  else if (v.length > 6) v = v.replace(/(\d{3})(\d{3})(\d{0,3})/, '$1.$2.$3');
  else if (v.length > 3) v = v.replace(/(\d{3})(\d{0,3})/, '$1.$2');
  inp.value = v;
  const raw = v.replace(/\D/g,'');
  const fmt = document.getElementById('cpfFmt');
  const tmpl = '___.___.___-__';
  let disp = '';
  let ri = 0;
  for (let i = 0; i < tmpl.length; i++) {
    if (tmpl[i] === '_') { disp += ri < raw.length ? raw[ri++] : '_'; }
    else disp += tmpl[i];
  }
  fmt.textContent = disp;
  fmt.style.color = raw.length === 11 ? 'var(--success)' : 'var(--ink-3)';
}

function checkStrength(pwd) {
  const segs = [document.getElementById('s1'), document.getElementById('s2'), document.getElementById('s3')];
  const lbl  = document.getElementById('strengthLabel');
  let score = 0;
  if (pwd.length >= 6) score++;
  if (/[a-zA-Z]/.test(pwd) && /\d/.test(pwd)) score++;
  if (pwd.length >= 10 && /[^a-zA-Z0-9]/.test(pwd)) score++;
  const cls   = ['weak','medium','strong'];
  const texts = ['Senha fraca','Senha razoável','Senha forte'];
  const colors= ['var(--danger)','#EF9F27','var(--success)'];
  segs.forEach((s, i) => { s.className = 'strength-seg' + (i < score ? ' ' + cls[score - 1] : ''); });
  if (pwd.length === 0) { lbl.textContent = 'Digite uma senha'; lbl.style.color = 'var(--ink-3)'; }
  else { lbl.textContent = texts[score - 1] || 'Senha muito curta'; lbl.style.color = score ? colors[score-1] : 'var(--danger)'; }
}

function checkConfirm() {
  const p1 = document.getElementById('regPwd').value;
  const p2 = document.getElementById('regPwdConfirm').value;
  const err = document.getElementById('regPwdConfirmErr');
  const inp = document.getElementById('regPwdConfirm');
  if (p2.length && p1 !== p2) { err.classList.add('show'); inp.classList.add('error'); inp.classList.remove('valid'); }
  else if (p2.length && p1 === p2) { err.classList.remove('show'); inp.classList.remove('error'); inp.classList.add('valid'); }
  else { err.classList.remove('show'); inp.classList.remove('error','valid'); }
}

function validateEmailField() {
  const v = document.getElementById('regEmail').value;
  const ok = /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(v);
  document.getElementById('regEmail').classList.toggle('valid', ok && v.length > 0);
}

function clearLoginAlert() {
  document.getElementById('loginAlert').classList.remove('show');
}

function showErr(id, errId) {
  document.getElementById(id).classList.add('error');
  document.getElementById(errId).classList.add('show');
}

function clearErr(id, errId) {
  document.getElementById(id).classList.remove('error');
  document.getElementById(errId).classList.remove('show');
}

// ── FUNÇÃO DE LOGIN CORRIGIDA ──────────────────────────────
async function doLogin() {
  const email = document.getElementById('loginEmail').value.trim();
  const pwd   = document.getElementById('loginPwd').value;
  let ok = true;

  clearErr('loginEmail','loginEmailErr');
  clearErr('loginPwd','loginPwdErr');

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { showErr('loginEmail','loginEmailErr'); ok = false; }
  if (!pwd) { showErr('loginPwd','loginPwdErr'); ok = false; }
  if (!ok) return;

  const btn = document.getElementById('loginBtn');
  btn.classList.add('loading');

  try {
    const response = await fetch('http://127.0.0.1:8000/api/login', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ email: email, senha: pwd })
    });

    const data = await response.json();

    if (response.ok) {
      document.getElementById('loginAlert').classList.remove('show');

      // ── CORREÇÃO 1: Salvar TODOS os dados necessários no localStorage ──
      localStorage.setItem('usuarioLogado', data.nome);
      localStorage.setItem('usuarioId',     data.id_usuario || data.id || '');
      localStorage.setItem('usuarioEmail',  data.email || email);
      // O backend deve retornar o campo "tipo": "cliente" | "organizador" | "colaborador"
      const tipo = data.tipo || 'cliente';
      localStorage.setItem('usuarioTipo', tipo);

      // Para o painel do organizador (usa chaves diferentes)
      if (tipo === 'organizador' || tipo === 'colaborador') {
        localStorage.setItem('orgLogado', data.nome);
        localStorage.setItem('orgId',     data.id_usuario || data.id || '');
        localStorage.setItem('orgTipo',   tipo);
      }

      // ── CORREÇÃO 2: Redirecionar conforme o tipo de usuário ──
      if (tipo === 'organizador' || tipo === 'colaborador') {
        window.location.href = 'painel_organizador.html';
      } else {
        // Clientes vão para a página principal
        window.location.href = 'index.html';
      }

    } else {
      document.getElementById('loginAlertMsg').textContent = data.detail || 'E-mail ou senha incorretos.';
      document.getElementById('loginAlert').classList.add('show');
    }
  } catch (error) {
    document.getElementById('loginAlertMsg').textContent = 'Erro de conexão. O servidor Python está rodando?';
    document.getElementById('loginAlert').classList.add('show');
  } finally {
    btn.classList.remove('loading');
  }
}

// Botão de teste — preenche com credenciais de cliente
function loginAsCliente() {
  document.getElementById('loginEmail').value = 'ana.lima@email.com';
  document.getElementById('loginPwd').value   = '123456';
  clearLoginAlert();
}

// ── REGISTRO ──────────────────────────────────────────────
async function doRegister() {
  const name  = document.getElementById('regName').value.trim();
  const email = document.getElementById('regEmail').value.trim();
  const cpf   = document.getElementById('regCpf').value.replace(/\D/g,'');
  const pwd   = document.getElementById('regPwd').value;
  const pwd2  = document.getElementById('regPwdConfirm').value;
  const terms = document.getElementById('termsCheck').checked;
  let ok = true;

  clearErr('regName','regNameErr');
  clearErr('regEmail','regEmailErr');
  clearErr('regCpf','regCpfErr');
  clearErr('regPwd','regPwdErr');
  clearErr('regPwdConfirm','regPwdConfirmErr');
  document.getElementById('registerAlert').classList.remove('show');

  if (name.split(' ').length < 2) { showErr('regName','regNameErr'); ok = false; }
  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) { showErr('regEmail','regEmailErr'); ok = false; }
  if (cpf.length !== 11) { showErr('regCpf','regCpfErr'); ok = false; }
  if (pwd.length < 6 || !/[a-zA-Z]/.test(pwd) || !/\d/.test(pwd)) { showErr('regPwd','regPwdErr'); ok = false; }
  if (pwd !== pwd2) { showErr('regPwdConfirm','regPwdConfirmErr'); ok = false; }
  if (!terms) {
    document.getElementById('registerAlertMsg').textContent = 'Aceite os Termos de Uso para continuar.';
    document.getElementById('registerAlert').style.display = 'flex';
    document.getElementById('registerAlert').classList.add('show');
    ok = false;
  }
  if (!ok) return;

  const btn = document.getElementById('registerBtn');
  btn.classList.add('loading');

  try {
    const response = await fetch('http://127.0.0.1:8000/api/registro', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ nome: name, email: email, cpf: cpf, senha: pwd, tipo: 'cliente' })
    });

    const data = await response.json();

    if (response.ok) {
      document.getElementById('registerForm').style.display = 'none';
      document.getElementById('successEmail').textContent = email;
      document.getElementById('successBox').classList.add('show');
    } else {
      document.getElementById('registerAlertMsg').textContent = data.detail || 'Erro ao criar conta.';
      document.getElementById('registerAlert').style.display = 'flex';
      document.getElementById('registerAlert').classList.add('show');
    }
  } catch (error) {
    document.getElementById('registerAlertMsg').textContent = 'Erro de conexão com o servidor.';
    document.getElementById('registerAlert').style.display = 'flex';
    document.getElementById('registerAlert').classList.add('show');
  } finally {
    btn.classList.remove('loading');
  }
}

// ── ESQUECI MINHA SENHA ───────────────────────────────────
function doForgot() {
  const emailEl = document.getElementById('forgotEmail');
  const email   = emailEl.value.trim();

  if (!/^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email)) {
    emailEl.classList.add('error');
    return;
  }
  emailEl.classList.remove('error');

  const btn = document.querySelector('#forgotForm .btn-submit');
  btn.classList.add('loading');

  // Simula envio (substitua por chamada real ao backend)
  setTimeout(() => {
    btn.classList.remove('loading');
    alert('📧 Se esse e-mail estiver cadastrado, você receberá o link em instantes.');
    switchTab('login');
  }, 1200);
}
