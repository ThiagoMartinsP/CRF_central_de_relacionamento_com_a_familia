# CRF — Central de Relacionamento com a Família

**Projeto:** Match Perfeito — Inteligência na Inscrição de Creche
**Escopo deste repositório:** apenas o recorte de captura (T0) descrito em
`docs/CRF - MVP Reduzido - Cadastro e Captura de Contatos.md`.

O fluxo implementado é: inscrição chega do matricula.rio → CRF grava responsável
e criança (chaveada pelo CPF da criança) → conversa guiada no WhatsApp pede até 2
contatos de apoio, um campo por vez → contatos ficam registrados **vinculados à
criança**.

Fora de escopo (deliberadamente): convocação de vaga, cascata de acionamento,
painel de unidade, score de confiabilidade, check-ins periódicos, integração real
com Cloud API / Evolution API.

---

## Rodando

Requer Python 3.12+ e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
```

### Demo completa (recomendado para ver o fluxo)

Roda a aplicação em processo, sem precisar subir servidor. Recria o banco a cada
execução e imprime a conversa inteira, campo a campo:

```bash
uv run python scripts/demo.py
```

Cobre os 9 cenários: captura completa de 2 contatos, fila de irmãos (seção 8.2),
respostas fora de formato (8.5), telefone duplicado, CPF ausente e CPF com dígito
verificador inválido (8.3), reenvio de inscrição, número desconhecido, o ciclo de
lembrete → expiração → destravamento da fila (8.4), reabertura por mensagem
tardia, e uma prova de que o limite de 2 contatos está travado no banco
(decisão 3).

### Servidor HTTP

```bash
uv run uvicorn app.main:app --reload
uv run python scripts/demo.py --base-url http://127.0.0.1:8000
```

Docs interativas em `http://127.0.0.1:8000/docs`.

### Variáveis de ambiente

| Variável | Padrão | Efeito |
|---|---|---|
| `CRF_DATABASE` | `./crf.db` | Caminho do arquivo SQLite |
| `CRF_VALIDAR_DV_CPF` | `1` | `0` desliga a validação do dígito verificador do CPF |
| `CRF_LEMBRETE_APOS_MIN` | `1440` (24h) | Silêncio da família até o lembrete |
| `CRF_EXPIRA_APOS_MIN` | `4320` (72h) | Silêncio da família até a sessão expirar |

---

## Estrutura

```
app/
  schema.sql      DDL (schema da spec traduzido para SQLite)
  db.py           conexão, PRAGMAs, transação explícita, migração de schema
  validadores.py  CPF (formato + DV), telefone E.164, parentesco, SIM/NÃO
  templates.py    templates de mensagem da seção 9
  mensageria.py   "envio" — grava em `mensagem` e devolve o texto renderizado
  captura.py      regra de disparo (seção 5) + máquina de estados (seção 6)
  main.py         endpoints (seção 4)
scripts/
  demo.py         roteiro CLI de demonstração
docs/
  especificação do recorte
```

---

## Endpoints

| Método | Rota | Papel |
|---|---|---|
| `POST` | `/webhooks/matricula-rio` | Simula o passo 1 — inscrição chega |
| `POST` | `/webhooks/whatsapp/inbound` | Simula o passo 3 — família responde |
| `POST` | `/manutencao/varrer-sessoes` | Aplica lembrete e expiração às sessões silenciosas (8.4) |
| `GET` | `/criancas/{cpf}` | Consulta de depuração — árvore de contato |
| `GET` | `/healthz` | Sanidade |

Não existe adapter de mensageria: "enviar" grava uma linha em `mensagem` com
`direcao = 'ENVIADA'` e devolve o texto renderizado no corpo da resposta, que é o
que a demo exibe.

---

## Banco: PostgreSQL da spec → SQLite

O schema da especificação é PostgreSQL. Como o ambiente não tem Postgres nem
Docker, foi traduzido para SQLite preservando **todas as garantias declarativas**.
Equivalências:

| Especificação (PostgreSQL) | Implementação (SQLite) |
|---|---|
| `CREATE TYPE ... AS ENUM` | `TEXT` + `CHECK (col IN (...))` |
| `UUID DEFAULT gen_random_uuid()` | `TEXT`, UUID gerado na aplicação |
| `CHAR(11) CHECK (cpf ~ '^\d{11}$')` | `TEXT CHECK (length(cpf)=11 AND cpf NOT GLOB '*[^0-9]*')` |
| `TIMESTAMPTZ DEFAULT now()` | `TEXT DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ','now'))` |
| `JSONB` | `TEXT CHECK (json_valid(...))` |
| `FUNCTION plpgsql` + `RAISE EXCEPTION` | `TRIGGER ... WHEN ... BEGIN SELECT RAISE(ABORT, ...) END` |
| Índice único parcial | Idêntico — SQLite suporta |

Dois pontos que exigem atenção nessa tradução:

1. **`cpf` é `TEXT PRIMARY KEY`, não `INTEGER`.** Em SQLite, só
   `INTEGER PRIMARY KEY` vira alias de `rowid` e sofre coerção numérica — é
   exatamente isso que apagaria os zeros à esquerda. A demo verifica com
   `typeof(cpf)` que o valor armazenado é `text`.
2. **Integridade referencial é desligada por padrão no SQLite e a configuração é
   por conexão.** Sem `PRAGMA foreign_keys = ON` (aplicado em `db.conectar()`),
   todos os `REFERENCES` do schema seriam decorativos.

Para migrar para Postgres depois: o `schema.sql` da spec vale como está, e a
camada de acesso usa SQL puro com placeholders posicionais — a troca é o driver e
o `?` → `%s`, não a lógica.

---

## Expiração de sessão (seção 8.4 da spec)

A spec deixa a sessão `EM_ANDAMENTO` para sempre quando a família não responde.
O sintoma óbvio é a família perdida; o grave é outro: como só existe **uma**
sessão ativa por responsável e a fila `captura_pendente` só é consultada no
encerramento, **uma conversa abandonada bloqueava permanentemente todas as
outras crianças daquele responsável**. A criança existia no banco, com inscrição
válida, e era invisível para o sistema sem nenhum sinal de erro.

### Ciclo implementado

```
família responde ──► relógio de silêncio zera, lembrete rearmado
                          │
              24h de silêncio (CRF_LEMBRETE_APOS_MIN)
                          ▼
                 M1_LEMBRETE_CAPTURA
            (retoma a pergunta exata onde parou)
                          │
              72h de silêncio (CRF_EXPIRA_APOS_MIN)
                          ▼
                  status = EXPIRADA
         rascunho descartado + fila destravada
                          │
              família escreve depois
                          ▼
                 M1_REABERTURA_CAPTURA
```

### Como a varredura é disparada

Sem worker em background, de propósito — o briefing adiou a complexidade de
polling para a fase de convocação (seção 2.1). São dois gatilhos complementares:

- **`POST /manutencao/varrer-sessoes`** — idempotente e sem estado próprio. É o
  que faz os lembretes saírem no prazo mesmo quando nada mais acontece no
  sistema. Chamável por Agendador de Tarefas/cron, ou na mão durante a demo.
- **Oportunista** — `processar_inscricao` varre as sessões daquele responsável
  antes de decidir o que fazer. É isso que garante que o bloqueio da fila **não
  sobreviva a uma nova inscrição**, independentemente de cron configurado.

### Detalhes que não são óbvios

1. **`ultima_resposta_em` é uma coluna separada de `atualizado_em`.** O relógio
   de silêncio só pode ser movido por uma resposta *da família*. Se a expiração
   fosse medida por `atualizado_em`, o próprio envio do lembrete reiniciaria a
   contagem e a sessão nunca venceria.
2. **`EXPIRADA` é um status distinto, não `CONCLUIDA`.** Chamar de concluída uma
   captura abandonada envenenaria a taxa de conclusão — que agora sai de graça
   como métrica.
3. **O rascunho é descartado na expiração.** Nome e parentesco sem telefone não
   formam um contato acionável.
4. **A mensagem tardia não é consumida como nome.** A captura reabre repetindo a
   pergunta. Um "oi" ou um emoji viraria um contato de apoio chamado "oi" — a
   pergunta repetida custa menos do que sujar a árvore.
5. **O índice único parcial continua indexando só `EM_ANDAMENTO`**, então uma
   sessão expirada não ocupa a vaga do responsável.
6. **Reabrir escolhe a criança**: a sessão expirada mais recente cuja criança
   ainda precisa de contatos; se não houver, a primeira da fila. Esse fallback
   também cura uma fila que tenha ficado órfã por qualquer outro motivo.

### Migração de schema

Isso exigiu uma coluna nova e alargar o `CHECK` de `status` — e SQLite não
permite alterar um `CHECK` existente. `db.py` reconstrói `conversa_captura`
preservando os dados (procedimento padrão de `ALTER TABLE` do SQLite: renomear,
recriar, copiar, dropar, recriar o índice). O gatilho é a **ausência da coluna**,
não `user_version`, porque bancos criados antes de existir versionamento têm
`user_version = 0` mesmo estando atualizados. Rodar em banco já atualizado é
no-op. Verificado contra um banco v1 com dados dentro: sessão preservada, CPF
ainda `text`, índice parcial recriado, sem tabela residual.

---

## Decisões de implementação além da especificação

Itens em que a spec não fecha o comportamento e o código teve de decidir. Todos
são reversíveis em um lugar só.

1. **`indice_contato` derivado, não fixo em 1.** A seção 5 fixa
   `indice_contato = 1` ao abrir a sessão. Se a criança ficou com 1 contato (a
   família respondeu NÃO) e a inscrição é reenviada, isso faria a captura
   perguntar "quer cadastrar mais um?" depois do 2º contato, e o `INSERT`
   seguinte bateria no trigger. `_abre_sessao` usa
   `total_contatos + 1` — como quem chama garante `total < 2`, o valor sempre cai
   no `CHECK (1, 2)`. Ver `app/captura.py`.
2. **`codigo_inscricao` já pertencente a outra criança → HTTP 409.** A coluna é
   `UNIQUE` e independente do CPF, então o upsert por CPF da seção 5 não cobre o
   caso. Payload inconsistente é rejeitado em vez de gerar erro de constraint.
3. **No upsert por CPF, o `codigo_inscricao` original é preservado** (só `nome` e
   `id_responsavel` são atualizados). Alternativa seria sobrescrever — não
   destrutivo por padrão.
4. **Telefone fixo é rejeitado.** O canal é WhatsApp, então
   `normaliza_e164_brasil` só aceita celular; número de 10 dígitos iniciado em
   6–9 recebe o nono dígito, iniciado em 2–5 (fixo) é recusado.
5. **`crianca_cpf` aceita `str | int`.** Se o CPF chegar como número no JSON, o
   normalizador aplica `zfill(11)` e recupera os zeros à esquerda em vez de
   deixar passar um valor de 10 dígitos.
6. **Validação do DV do CPF rejeita com 422**, conforme seção 7 (validação na
   aplicação, não no banco), com escape por `CRF_VALIDAR_DV_CPF=0` porque a spec
   admite dado sintético que não passe no cálculo. Os CPFs da demo são gerados
   com DV válido.
7. **Quatro templates a mais.** A spec descreve o comportamento sem nomear o
   template: `M1_PEDE_NOME_SEGUNDO`, `ERRO_NOME_VAZIO`,
   `ERRO_TELEFONE_DUPLICADO` (obrigatório — a constraint
   `UNIQUE (cpf_crianca, telefone_e164)` existe e precisa de resposta ao
   usuário), `ERRO_LIMITE_CONTATOS` (defensivo, para o trigger).
8. **`GET /criancas/{cpf}` devolve também o bloco `captura`** (sessão ativa com
   etapa e dados parciais, e se a criança está na fila). É endpoint de
   depuração; a spec pede criança + responsável + contatos.
9. **A mensagem do trigger não interpola o CPF.** `RAISE(ABORT)` do SQLite só
   aceita literal, então usa o prefixo estável `CRF_MAX_CONTATOS_APOIO:`, que a
   aplicação distingue de uma violação de `UNIQUE`.
10. **A reabertura por mensagem tardia encosta em autoatendimento**, que a seção
    10 da spec põe fora de escopo. Foi uma decisão explícita: ignorar uma família
    que está justamente colaborando custa mais do que o desvio de escopo. Fica
    contido — a mensagem tardia só retoma uma captura que já existia, não permite
    iniciar nada novo.

---

## Arestas conhecidas (herdadas da spec, não corrigidas de propósito)

- **Os lembretes dependem de alguém chamar a varredura.** Sem cron configurado, a
  expiração só acontece quando uma nova inscrição daquele responsável chega. O
  bloqueio da fila não sobrevive; o lembrete pontual, sim.
- **Um único lembrete por período de silêncio.** Ele é rearmado a cada resposta
  da família, então uma família que responde e para de novo recebe outro — mas
  não há escalonamento (2º, 3º lembrete).
- **Resposta não reconhecida em `CONFIRMAR_PROXIMO` encerra a sessão.** A seção
  6.1 diz "senão → encerrar", então "talvez" ou "hmm" fecham a captura como se
  fossem NÃO. Implementado ao pé da letra; vale reconsiderar.
- **Seção 8.1 — fadiga entre irmãos.** Por decisão 5 (âncora na criança), a
  família cadastra os mesmos contatos uma vez por criança. A demo mostra isso
  acontecendo. Trade-off aceito, não bug.
- **Seção 8.5 — sem limite de tentativas** em resposta fora de formato.
- **Sem autenticação nos webhooks.** Nenhum dos dois endpoints valida origem ou
  assinatura.

---

## Pontos da spec que continuam abertos (seção 11)

1. Confirmar com a SME que o matricula.rio coleta e valida o CPF **da criança**
   no ato da inscrição — é o requisito que decide se `crianca.cpf` como chave
   primária sobrevive fora do protótipo.
2. Criança sem CPF (8.3) hoje é rejeitada com 422 e não entra no banco. A
   alternativa registrada na spec é `cpf UNIQUE` + UUID substituto.
3. Atalho futuro para reaproveitar contatos entre irmãos ("usar os mesmos
   contatos de [CRIANCA_1]? SIM/NÃO").
