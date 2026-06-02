const API_BASE = 'http://127.0.0.1:8000/api';

let currentCategory = 'todos';
let currentEvent = null;
let currentQty = 1;
let selectedLoteIndex = 0;
let eventosReais = [];

// ── CARREGAR EVENTOS DO BANCO ─────────────────────────────────────────────────
async function carregarEventos() {
    try {
        const response = await fetch(`${API_BASE}/eventos`);

        if (!response.ok) throw new Error('Resposta inválida do servidor');

        eventosReais = await response.json();

        // Enriquece cada evento com vagas_disponiveis reais do banco.
        // Faz todas as requisições em paralelo para não travar a página.
        await Promise.all(eventosReais.map(async (ev) => {
            try {
                const vagasRes = await fetch(`${API_BASE}/vagas/${ev.id_evento}`);
                if (vagasRes.ok) {
                    const vagas = await vagasRes.json();
                    ev.vagas_disponiveis = Math.max(0, parseInt(vagas.vagas_disponiveis) || 0);
                } else {
                    ev.vagas_disponiveis = ev.capacidade_maxima;
                }
            } catch (_) {
                ev.vagas_disponiveis = ev.capacidade_maxima;
            }
        }));

        renderEvents(eventosReais);
        atualizarHeroCard(eventosReais[0] || null);

    } catch (error) {
        console.error('Erro ao carregar eventos:', error);
        eventosReais = [];
        renderEvents([]);
        atualizarHeroCard(null);
        showToast('⚠️ Não foi possível conectar ao servidor.');
    }
}

// ── HERO CARD DINÂMICO ────────────────────────────────────────────────────────
function atualizarHeroCard(ev) {
    const heroVisual = document.querySelector('.hero-visual');
    if (!heroVisual) return;

    if (!ev) {
        heroVisual.innerHTML = `
            <div class="ticket-card" style="opacity:0.4; cursor:default;">
                <div class="ticket-img banner-rock">
                    <div class="ticket-img-text">—</div>
                </div>
                <div class="ticket-body">
                    <h3>Nenhum evento disponível</h3>
                    <div class="ticket-meta"><span>Aguardando eventos do banco de dados</span></div>
                </div>
            </div>`;
        return;
    }

    const dataFormatada = ev.data_hora
        ? new Date(ev.data_hora).toLocaleDateString('pt-BR', { day:'2-digit', month:'short', year:'numeric' })
        : 'Data a definir';
    const categoria = ev.categoria || 'outros';
    const bannerClass = `banner-${categoria}`;
    const bannerText = categoria.toUpperCase().slice(0, 4);

    heroVisual.innerHTML = `
        <div class="ticket-card" onclick="openModal('${ev.id_evento}')">
            <div class="ticket-img ${bannerClass}">
                <div class="ticket-img-pattern"></div>
                <div class="ticket-img-text">${bannerText}</div>
                <div class="ticket-genre-tag">${categoria.charAt(0).toUpperCase() + categoria.slice(1)}</div>
            </div>
            <div class="ticket-body">
                <h3>${ev.titulo}</h3>
                <div class="ticket-meta">
                    <span>📅 ${dataFormatada}</span>
                    <span>📍 ${(ev.local || '').split('—')[0].trim()}</span>
                </div>
                <hr class="ticket-divider">
                <div class="ticket-footer">
                    <div class="ticket-price">
                        Ver preços
                        <small>no evento</small>
                    </div>
                    <div class="qr-placeholder" id="hero-qr">
                        <div></div><div></div><div></div><div></div><div></div>
                        <div></div><div></div><div></div><div></div><div></div>
                        <div></div><div></div><div></div><div></div><div></div>
                        <div></div><div></div><div></div><div></div><div></div>
                        <div></div><div></div><div></div><div></div><div></div>
                    </div>
                </div>
            </div>
        </div>
        <div class="floating-badge badge-1">
            <div class="badge-dot"></div>
            <span>${ev.vagas_disponiveis > 0 ? ev.vagas_disponiveis + ' ingressos disponíveis' : 'Esgotado'}</span>
        </div>`;
}

// ── RENDERIZAR GRID DE EVENTOS ────────────────────────────────────────────────
function renderEvents(list) {
    const grid = document.getElementById('eventsGrid');
    if (!list.length) {
        grid.innerHTML = '<p style="color:var(--ink-3); font-size:0.9375rem; grid-column:1/-1; padding:2rem 0;">Nenhum evento encontrado.</p>';
        return;
    }
    grid.innerHTML = list.map(ev => {
        const dataFormatada = ev.data_hora ? new Date(ev.data_hora).toLocaleDateString('pt-BR') : 'Data a definir';
        const horaFormatada = ev.data_hora ? new Date(ev.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';
        const categoria = ev.categoria || 'outros';
        const bannerClass = `banner-${categoria}`;
        const bannerText = categoria.toUpperCase().slice(0, 4);
        const disponivel = ev.vagas_disponiveis > 0;

        return `
            <div class="event-card" onclick="${disponivel ? `openModal('${ev.id_evento}')` : ''}" style="${disponivel ? '' : 'cursor:default;opacity:0.7'}">
                <div class="event-banner ${bannerClass}">
                    <div class="banner-text">${bannerText}</div>
                    <span class="event-category">${categoria}</span>
                    <button class="event-fav" onclick="event.stopPropagation(); toggleFav(this)" title="Favoritar">♡</button>
                    <span class="event-available ${!disponivel ? 'event-sold-out' : ''}">${disponivel ? ev.vagas_disponiveis + ' vagas' : 'Esgotado'}</span>
                </div>
                <div class="event-body">
                    <div class="event-date-badge">📅 ${dataFormatada} · ${horaFormatada}</div>
                    <div class="event-title">${ev.titulo}</div>
                    <div class="event-venue">📍 ${ev.local}</div>
                    <div class="event-footer">
                        <div class="event-price-tag">
                            <span class="price-from">ingressos</span>
                            <span class="price-value">ver preços</span>
                        </div>
                        <button class="btn-buy ${!disponivel ? 'btn-buy-disabled' : ''}" onclick="event.stopPropagation(); ${disponivel ? `openModal('${ev.id_evento}')` : ''}">
                            ${disponivel ? 'Comprar' : 'Esgotado'}
                        </button>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// ── MODAL ─────────────────────────────────────────────────────────────────────
async function openModal(eventoId) {
    const ev = eventosReais.find(e => e.id_evento == eventoId);
    if (!ev) return;

    currentEvent = ev;
    currentQty = 1;
    selectedLoteIndex = 0;

    const dataFormatada = ev.data_hora ? new Date(ev.data_hora).toLocaleDateString('pt-BR') : 'Data a definir';
    const horaFormatada = ev.data_hora ? new Date(ev.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';
    const categoria = ev.categoria || 'outros';
    const disponivel = ev.vagas_disponiveis > 0;

    document.getElementById('modalBanner').className = 'modal-banner banner-' + categoria;
    document.getElementById('modalBannerText').textContent = categoria.toUpperCase().slice(0, 4);
    document.getElementById('modalTitle').textContent = ev.titulo;
    document.getElementById('modalMeta').innerHTML = `
        <span>📅 ${dataFormatada} às ${horaFormatada}</span>
        <span>📍 ${ev.local}</span>
        <span>🎟 ${disponivel ? ev.vagas_disponiveis + ' ingressos disponíveis' : 'Esgotado'}</span>
    `;

    // Mostra o modal imediatamente com estado de carregando
    document.getElementById('lotesContainer').innerHTML = `
        <div style="color:var(--ink-3); font-size:0.9rem; padding:1rem 0;">Carregando tipos de ingresso…</div>
    `;
    document.getElementById('modalOverlay').classList.add('open');
    document.body.style.overflow = 'hidden';

    // Busca lotes reais do banco
    let lotes = [];
    try {
        const res = await fetch(`${API_BASE}/eventos/${ev.id_evento}/lotes`);
        if (res.ok) {
            lotes = await res.json();
        }
    } catch (err) {
        console.warn('Erro ao buscar lotes:', err);
    }

    // Guarda os lotes no evento atual para uso em updateTotal/confirmPurchase
    currentEvent._lotes = lotes;

    if (!lotes.length) {
        document.getElementById('lotesContainer').innerHTML = `
            <div style="color:var(--ink-3); font-size:0.9rem; padding:0.5rem 0; font-style:italic;">
                Nenhum tipo de ingresso cadastrado para este evento.
            </div>
        `;
        document.getElementById('totalDisplay').textContent = 'R$ —';
        return;
    }

    document.getElementById('lotesContainer').innerHTML = lotes.map((l, i) => `
        <div class="lote-option ${i===0 ? 'selected' : ''}" onclick="selectLote(${i}, this)">
            <div>
                <div class="lote-name">${l.nome}</div>
                <div class="lote-avail">${l.quantidade > 0 ? l.quantidade + ' disponíveis' : 'Esgotado'}</div>
            </div>
            <div class="lote-price">R$&nbsp;${Number(l.preco).toFixed(2).replace('.', ',')}</div>
        </div>
    `).join('');

    updateTotal();
    document.getElementById('qtyDisplay').textContent = 1;
}

function selectLote(i, el) {
    selectedLoteIndex = i;
    document.querySelectorAll('.lote-option').forEach(o => o.classList.remove('selected'));
    el.classList.add('selected');
    updateTotal();
}

function changeQty(d) {
    if (!currentEvent) return;
    const max = currentEvent.vagas_disponiveis ?? currentEvent.capacidade_maxima ?? 100;
    currentQty = Math.max(1, Math.min(currentQty + d, max));
    document.getElementById('qtyDisplay').textContent = currentQty;
    updateTotal();
}

function updateTotal() {
    if (!currentEvent) return;
    const lotes = currentEvent._lotes || [];
    if (!lotes.length) {
        document.getElementById('totalDisplay').textContent = 'R$ —';
        return;
    }
    const preco = lotes[selectedLoteIndex]?.preco || 0;
    const total = (preco * currentQty).toFixed(2).replace('.', ',');
    document.getElementById('totalDisplay').textContent = 'R$ ' + total;
}

async function confirmPurchase() {
    const clienteId   = localStorage.getItem('usuarioId');
    const clienteNome = localStorage.getItem('usuarioLogado');

    if (!clienteId && !clienteNome) {
        showToast('❌ Faça login antes de comprar ingressos');
        setTimeout(() => { window.location.href = 'login.html'; }, 1500);
        return;
    }

    const lotes = currentEvent._lotes || [];
    if (!lotes.length) {
        showToast('❌ Este evento não possui tipos de ingresso cadastrados.');
        return;
    }

    const loteSelecionado = lotes[selectedLoteIndex];
    const preco    = loteSelecionado.preco;
    const loteNome = loteSelecionado.nome;
    const total    = preco * currentQty;

    const agora = new Date();
    const dataFormatada = currentEvent.data_hora ? new Date(currentEvent.data_hora).toLocaleDateString('pt-BR') : agora.toLocaleDateString('pt-BR');
    const horaFormatada = currentEvent.data_hora ? new Date(currentEvent.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : agora.toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' });
    const categoria  = currentEvent.categoria || 'outros';
    const bannerClass = `banner-${categoria}`;
    const bannerText  = categoria.toUpperCase().slice(0, 4);

    const payload = {
        id_evento:       currentEvent.id_evento,
        id_cliente:      clienteId || "11122233-3440-0000-0000-000000000001",
        titulo_evento:   currentEvent.titulo,
        data_evento:     currentEvent.data_hora || agora.toISOString(),
        local_evento:    currentEvent.local,
        valor_pago:      total,
        forma_pagamento: "pix"
    };

    try {
        const response = await fetch(`${API_BASE}/tickets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });

        if (response.ok) {
            const ticket = await response.json();
            closeModal();
            showToast(`🎉 Ingresso comprado! Código: ${ticket.codigo_qr}`);
        } else {
            const erro = await response.json();
            showToast(`❌ Erro: ${erro.detail || 'Ingressos esgotados'}`);
            closeModal();
            return;
        }
    } catch (error) {
        console.error('Erro na compra:', error);
        showToast('🎉 Modo demonstração: Ingresso reservado!');
        closeModal();
    }

    setTimeout(() => {
        window.location.href = `pagamento.html?titulo=${encodeURIComponent(currentEvent.titulo)}&preco=${preco}&qty=${currentQty}&data=${encodeURIComponent(dataFormatada)}&hora=${encodeURIComponent(horaFormatada)}&local=${encodeURIComponent(currentEvent.local)}&banner=${bannerClass}&texto=${bannerText}&lote=${encodeURIComponent(loteNome)}&evento_id=${currentEvent.id_evento}`;
    }, 500);
}

// ── FILTROS ───────────────────────────────────────────────────────────────────
function setCategory(cat, btn) {
    currentCategory = cat;
    document.querySelectorAll('.filter-chip').forEach(c => c.classList.remove('active'));
    btn.classList.add('active');
    filterEvents();
}

function filterEvents() {
    const q = document.getElementById('searchInput').value.toLowerCase();
    let list = eventosReais;
    if (currentCategory !== 'todos') {
        list = list.filter(e => (e.categoria || 'outros').toLowerCase() === currentCategory.toLowerCase());
    }
    if (q) {
        list = list.filter(e => e.titulo.toLowerCase().includes(q) || (e.local || '').toLowerCase().includes(q));
    }
    renderEvents(list);
}

// ── MODAL HELPERS ─────────────────────────────────────────────────────────────
function closeModal() {
    document.getElementById('modalOverlay').classList.remove('open');
    document.body.style.overflow = '';
}

function closeModalOutside(e) {
    if (e.target === document.getElementById('modalOverlay')) closeModal();
}

function toggleFav(btn) {
    btn.textContent = btn.textContent === '♡' ? '♥' : '♡';
    btn.style.color = btn.textContent === '♥' ? '#7991fc' : '';
}

function showToast(msg) {
    const t = document.getElementById('toast');
    document.getElementById('toastMsg').textContent = msg;
    t.classList.add('show');
    setTimeout(() => t.classList.remove('show'), 4000);
}

// ── LOGIN / LOGOUT ────────────────────────────────────────────────────────────
function verificarEstadoLogin() {
    const nomeUsuario = localStorage.getItem('usuarioLogado');
    if (nomeUsuario) {
        const primeiroNome = nomeUsuario.split(' ')[0];
        const navCta = document.querySelector('.nav-cta');
        navCta.innerHTML = `
            <span style="font-weight:600; color:var(--ink); margin-right:1rem;">👋 Bem-vindo(a), ${primeiroNome}</span>
            <a href="meus_ingressos.html" class="btn-ghost" style="text-decoration:none;">Meus Ingressos</a>
            <button onclick="fazerLogout()" class="btn-outline" style="padding:0.4rem 1rem; border-radius:var(--r-sm);">Sair</button>
        `;
    }
}

function fazerLogout() {
    localStorage.removeItem('usuarioLogado');
    localStorage.removeItem('usuarioId');
    window.location.reload();
}

// ── INIT ──────────────────────────────────────────────────────────────────────
document.addEventListener('DOMContentLoaded', () => {
    carregarEventos();
    verificarEstadoLogin();
});