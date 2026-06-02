import http from 'k6/http';
import { check, sleep } from 'k6';

export let options = {
  stages: [
    { duration: '10s', target: 10  },
    { duration: '20s', target: 50  },
    { duration: '10s', target: 100 },
    { duration: '10s', target: 0   },
  ],
  thresholds: {
    http_req_duration: ['p(95)<2000'],  
    http_req_failed:   ['rate<0.05'],   
  },
};

export default function () {
  const url = 'http://127.0.0.1:8000/api/registro';

  // Índice global único por (VU, iteração) — evita colisão de e-mail e CPF
  // entre todos os VUs em todas as iterações do teste.
  const idx   = (__VU - 1) * 10000 + __ITER;
  const email = `teste_${__VU}_${__ITER}@email.com`;

  // CPF: 11 dígitos, único por índice, sem formatação (o backend remove pontos/traços)
  const cpf   = String(idx).padStart(11, '0');

  const payload = JSON.stringify({
    nome:  `Usuario Teste ${idx}`,
    email: email,
    cpf:   cpf,
    senha: 'Senha123',   
    tipo:  'cliente',    
  });

  const params = { headers: { 'Content-Type': 'application/json' } };

  const res = http.post(url, payload, params);

  check(res, {
    'status 201':   (r) => r.status === 201,
    'response ok':  (r) => r.json('sucesso') === true,
  });

  sleep(1);
}