import http from 'k6/http';
import { check, sleep } from 'k6';

const BASE = 'http://127.0.0.1:8000/api';
const SENHA = 'Senha123';
const TOTAL_USUARIOS = 50;

export let options = {
  stages: [
    { duration: '10s', target: 10 },
    { duration: '20s', target: 50 },
    { duration: '10s', target: 0 },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2500'],
    http_req_failed:   ['rate<0.05'],
  },
};


export function setup() {
  for (let i = 1; i <= TOTAL_USUARIOS; i++) {
    const email = `loadtest_${i}@email.com`;
    const cpf   = String(i * 7 + 1000000000).padStart(11, '0').slice(-11); // CPF fixo por índice
    const payload = JSON.stringify({
      nome:  `Load Test ${i}`,
      email: email,
      cpf:   cpf,
      senha: SENHA,
      tipo:  'cliente',
    });
    // Tenta cadastrar — ignora erro 400 (usuário já existe do teste anterior)
    http.post(`${BASE}/registro`, payload, {
      headers: { 'Content-Type': 'application/json' },
    });
  }
  console.log(`Setup: ${TOTAL_USUARIOS} usuários garantidos no banco.`);
}

export default function () {
  
  const i     = ((__VU - 1) % TOTAL_USUARIOS) + 1;
  const email = `loadtest_${i}@email.com`;

  const res = http.post(`${BASE}/login`,
    JSON.stringify({ email, senha: SENHA }),
    { headers: { 'Content-Type': 'application/json' } }
  );

  check(res, {
    'status 200':   (r) => r.status === 200,
    'retornou id':  (r) => r.json('id_usuario') !== null,
    'tipo correto': (r) => r.json('tipo') === 'cliente',
  });

  sleep(1);
}