const API_BASE = 'http://127.0.0.1:8000/api';

let currentCategory = 'todos';
let currentEvent = null;
let currentQty = 1;
let selectedLoteIndex = 0;
let eventosReais = [];

const EVENTOS_EXEMPLO = [
    { titulo: "Rock in Rio de Janeiro 2026", categoria: "rock", data_hora: "2026-09-15T19:00:00", local: "Cidade do Rock — Barra da Tijuca, RJ", capacidade_maxima: 5000, descricao: "Festival de rock com grandes atrações nacionais e internacionais." },
    { titulo: "Noite do Samba — Edição Especial", categoria: "samba", data_hora: "2026-07-20T20:00:00", local: "Fundição Progresso — Lapa, RJ", capacidade_maxima: 800, descricao: "Uma noite especial com os maiores nomes do samba carioca." },
    { titulo: "Festival de Jazz na Praia", categoria: "jazz", data_hora: "2026-08-10T18:00:00", local: "Praia de Copacabana — RJ", capacidade_maxima: 3000, descricao: "Jazz, blues e música instrumental à beira-mar." },
    { titulo: "Show de Pop Internacional", categoria: "pop", data_hora: "2026-10-05T21:00:00", local: "Estádio Nilton Santos — Engenhão, RJ", capacidade_maxima: 40000, descricao: "Grandes nomes do pop mundial em show único." },
    { titulo: "Feira de Música Independente", categoria: "indie", data_hora: "2026-11-20T14:00:00", local: "Centro de Convenções — Barra da Tijuca, RJ", capacidade_maxima: 1500, descricao: "Descubra novos talentos e bandas independentes." }
];

async function carregarEventos() {
    try {
        const response = await fetch(`${API_BASE}/eventos`);
        
        if (response.ok) {
            eventosReais = await response.json();
            
            if (eventosReais.length === 0) {
                console.log('Banco vazio. Populando com eventos exemplo...');
                await semearEventosExemplo();
                const novaResposta = await fetch(`${API_BASE}/eventos`);
                eventosReais = await novaResposta.json();
            }
        } else {
            throw new Error('Erro ao carregar eventos');
        }
        
        renderEvents(eventosReais);
    } catch (error) {
        console.error('Erro na API:', error);
        eventosReais = EVENTOS_EXEMPLO.map((ev, idx) => ({ ...ev, id_evento: String(idx + 1) }));
        renderEvents(eventosReais);
        showToast('⚠️ Modo offline - usando dados de demonstração');
    }
}

async function semearEventosExemplo() {
    const organizadorId = await garantirOrganizadorPadrao();
    
    if (!organizadorId) {
        console.error('Não foi possível criar organizador padrão');
        return;
    }
    
    for (const evento of EVENTOS_EXEMPLO) {
        try {
            const response = await fetch(`${API_BASE}/eventos?id_organizador=${organizadorId}`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(evento)
            });
            
            if (!response.ok) {
                console.error(`Erro ao criar evento "${evento.titulo}"`);
            } else {
                console.log(`Evento criado: ${evento.titulo}`);
            }
        } catch (error) {
            console.error(`Erro ao criar evento "${evento.titulo}":`, error);
        }
    }
}

async function garantirOrganizadorPadrao() {
    const loginPayload = {
        email: "contato@djprod.com",
        senha: "123456"
    };
    
    try {
        const response = await fetch(`${API_BASE}/login`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(loginPayload)
        });
        
        if (response.ok) {
            const data = await response.json();
            return data.id_usuario;
        }
    } catch (error) {
        console.log('Organizador padrão não encontrado, tentando criar...');
    }
    
    try {
        const registroPayload = {
            nome: "DJ Productions",
            email: "contato@djprod.com",
            cpf: "44455566677",
            senha: "123456",
            tipo: "organizador",
            nome_organizacao: "DJ Productions Ltda",
            tipo_organizacao: "produtora"
        };
        
        const response = await fetch(`${API_BASE}/registro/organizador`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(registroPayload)
        });
        
        if (response.ok) {
            const loginResponse = await fetch(`${API_BASE}/login`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ email: "contato@djprod.com", senha: "123456" })
            });
            
            if (loginResponse.ok) {
                const data = await loginResponse.json();
                return data.id_usuario;
            }
        }
    } catch (error) {
        console.error('Erro ao criar organizador padrão:', error);
    }
    
    return null;
}

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
        const disponivel = ev.capacidade_maxima > 0;
        
        return `
            <div class="event-card" onclick="${disponivel ? `openModal('${ev.id_evento}')` : ''}" style="${disponivel ? '' : 'cursor:default;opacity:0.7'}">
                <div class="event-banner ${bannerClass}">
                    <div class="banner-text">${bannerText}</div>
                    <span class="event-category">${categoria}</span>
                    <button class="event-fav" onclick="event.stopPropagation(); toggleFav(this)" title="Favoritar">♡</button>
                    <span class="event-available ${!disponivel ? 'event-sold-out' : ''}">${disponivel ? ev.capacidade_maxima + ' vagas' : 'Esgotado'}</span>
                </div>
                <div class="event-body">
                    <div class="event-date-badge">📅 ${dataFormatada} · ${horaFormatada}</div>
                    <div class="event-title">${ev.titulo}</div>
                    <div class="event-venue">📍 ${ev.local}</div>
                    <div class="event-footer">
                        <div class="event-price-tag">
                            <span class="price-from">a partir de</span>
                            <span class="price-value">R$&nbsp;50</span>
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

async function openModal(eventoId) {
    const ev = eventosReais.find(e => e.id_evento == eventoId);
    if (!ev) return;
    
    currentEvent = ev;
    currentQty = 1;
    selectedLoteIndex = 0;

    const dataFormatada = ev.data_hora ? new Date(ev.data_hora).toLocaleDateString('pt-BR') : 'Data a definir';
    const horaFormatada = ev.data_hora ? new Date(ev.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : '';
    const categoria = ev.categoria || 'outros';
    const bannerClass = `banner-${categoria}`;
    const bannerText = categoria.toUpperCase().slice(0, 4);
    const disponivel = ev.capacidade_maxima > 0;

    document.getElementById('modalBanner').className = 'modal-banner ' + bannerClass;
    document.getElementById('modalBannerText').textContent = bannerText;
    document.getElementById('modalTitle').textContent = ev.titulo;
    document.getElementById('modalMeta').innerHTML = `
        <span>📅 ${dataFormatada} às ${horaFormatada}</span>
        <span>📍 ${ev.local}</span>
        <span>🎟 ${disponivel ? ev.capacidade_maxima + ' ingressos disponíveis' : 'Esgotado'}</span>
    `;

    const lotesMock = [
        { name: "Pista — 1º Lote", price: 150, available: disponivel ? Math.min(ev.capacidade_maxima, 100) : 0 },
        { name: "Pista — 2º Lote", price: 200, available: disponivel ? Math.min(ev.capacidade_maxima, 200) : 0 },
        { name: "Camarote VIP", price: 450, available: disponivel ? Math.min(ev.capacidade_maxima, 50) : 0 }
    ];

    const lotesCont = document.getElementById('lotesContainer');
    lotesCont.innerHTML = lotesMock.map((l, i) => `
        <div class="lote-option ${i===0 ? 'selected' : ''}" onclick="selectLote(${i}, this)">
            <div>
                <div class="lote-name">${l.name}</div>
                <div class="lote-avail">${l.available > 0 ? l.available + ' disponíveis' : 'Esgotado'}</div>
            </div>
            <div class="lote-price">R$&nbsp;${l.price}</div>
        </div>
    `).join('');

    updateTotal();
    document.getElementById('qtyDisplay').textContent = 1;
    document.getElementById('modalOverlay').classList.add('open');
    document.body.style.overflow = 'hidden';
}

function selectLote(i, el) {
    selectedLoteIndex = i;
    document.querySelectorAll('.lote-option').forEach(o => o.classList.remove('selected'));
    el.classList.add('selected');
    updateTotal();
}

function changeQty(d) {
    if (!currentEvent) return;
    const max = currentEvent.capacidade_maxima || 100;
    currentQty = Math.max(1, Math.min(currentQty + d, max || 1));
    document.getElementById('qtyDisplay').textContent = currentQty;
    updateTotal();
}

function updateTotal() {
    if (!currentEvent) return;
    const prices = [150, 200, 450];
    const price = prices[selectedLoteIndex] || 150;
    const total = (price * currentQty).toFixed(2).replace('.', ',');
    document.getElementById('totalDisplay').textContent = 'R$ ' + total;
}

async function confirmPurchase() {
    const clienteId = localStorage.getItem('usuarioId');
    const clienteNome = localStorage.getItem('usuarioLogado');
    
    if (!clienteId && !clienteNome) {
        showToast('❌ Faça login antes de comprar ingressos');
        setTimeout(() => { window.location.href = 'login.html'; }, 1500);
        return;
    }

    const preco = [150, 200, 450][selectedLoteIndex];
    const total = preco * currentQty;
    const agora = new Date();
    const ano = agora.getFullYear();
    const mes = String(agora.getMonth() + 1).padStart(2, '0');
    const dia = String(agora.getDate()).padStart(2, '0');
    const horas = String(agora.getHours()).padStart(2, '0');
    const minutos = String(agora.getMinutes()).padStart(2, '0');
    const segundos = String(agora.getSeconds()).padStart(2, '0');
    
    const payload = {
        id_evento: currentEvent.id_evento,
        id_cliente: clienteId || "11122233-3440-0000-0000-000000000001",
        titulo_evento: currentEvent.titulo,
        data_evento: currentEvent.data_hora || `${ano}-${mes}-${dia}T${horas}:${minutos}:${segundos}`,
        local_evento: currentEvent.local,
        valor_pago: total,
        forma_pagamento: "pix"
    };

    const dataFormatada = currentEvent.data_hora ? new Date(currentEvent.data_hora).toLocaleDateString('pt-BR') : `${dia}/${mes}/${ano}`;
    const horaFormatada = currentEvent.data_hora ? new Date(currentEvent.data_hora).toLocaleTimeString('pt-BR', { hour: '2-digit', minute: '2-digit' }) : `${horas}:${minutos}`;
    const categoria = currentEvent.categoria || 'outros';
    const bannerClass = `banner-${categoria}`;
    const bannerText = categoria.toUpperCase().slice(0, 4);
    const loteNome = ["Pista — 1º Lote", "Pista — 2º Lote", "Camarote VIP"][selectedLoteIndex];

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
            setTimeout(() => {
                window.location.href = `pagamento.html?titulo=${encodeURIComponent(currentEvent.titulo)}&preco=${preco}&qty=${currentQty}&data=${encodeURIComponent(dataFormatada)}&hora=${encodeURIComponent(horaFormatada)}&local=${encodeURIComponent(currentEvent.local)}&banner=${bannerClass}&texto=${bannerText}&lote=${encodeURIComponent(loteNome)}&evento_id=${currentEvent.id_evento}`;
            }, 1000);
        } else {
            const erro = await response.json();
            showToast(`❌ Erro: ${erro.detail || 'Ingressos esgotados'}`);
            closeModal();
        }
    } catch (error) {
        console.error('Erro na compra:', error);
        showToast('🎉 Modo demonstração: Ingresso reservado!');
        closeModal();
        setTimeout(() => {
            window.location.href = `pagamento.html?titulo=${encodeURIComponent(currentEvent.titulo)}&preco=${preco}&qty=${currentQty}&data=${encodeURIComponent(dataFormatada)}&hora=${encodeURIComponent(horaFormatada)}&local=${encodeURIComponent(currentEvent.local)}&banner=${bannerClass}&texto=${bannerText}&lote=${encodeURIComponent(loteNome)}&evento_id=${currentEvent.id_evento}`;
        }, 500);
    }
}

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

function verificarEstadoLogin() {
    const nomeUsuario = localStorage.getItem('usuarioLogado');
    if (nomeUsuario) {
        const primeiroNome = nomeUsuario.split(' ')[0];
        const navCta = document.querySelector('.nav-cta');
        navCta.innerHTML = `
            <span style="font-weight: 600; color: var(--ink); margin-right: 1rem;">👋 Bem-vindo(a), ${primeiroNome}</span>
            <a href="meus_ingressos.html" class="btn-ghost" style="text-decoration:none;">Meus Ingressos</a>
            <button onclick="fazerLogout()" class="btn-outline" style="padding: 0.4rem 1rem; border-radius: var(--r-sm);">Sair</button>
        `;
    }
}

function fazerLogout() {
    localStorage.removeItem('usuarioLogado');
    localStorage.removeItem('usuarioId');
    window.location.reload();
}

document.addEventListener('DOMContentLoaded', () => {
    carregarEventos();
    verificarEstadoLogin();
});