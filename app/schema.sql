-- CRF - MVP reduzido: cadastro e captura de contatos de apoio (recorte T0)
--
-- Schema da especificacao (PostgreSQL) traduzido para SQLite. Equivalencias:
--   CREATE TYPE ... AS ENUM        -> TEXT + CHECK (col IN (...))
--   UUID DEFAULT gen_random_uuid() -> TEXT, UUID gerado na aplicacao
--   CHAR(11) CHECK (cpf ~ '...')   -> TEXT + CHECK (length + NOT GLOB)
--   TIMESTAMPTZ DEFAULT now()      -> TEXT ISO-8601 UTC via strftime
--   JSONB                          -> TEXT + CHECK (json_valid(...))
--   FUNCTION plpgsql + RAISE       -> TRIGGER ... SELECT RAISE(ABORT, ...)
--   indice unico parcial           -> identico (SQLite suporta)

-- ---------- RESPONSAVEL ----------
-- Continua existindo como canal de mensageria (telefone), mas deixou de ser a
-- ancora da arvore de contato (decisao 5).
CREATE TABLE IF NOT EXISTS responsavel (
  id             TEXT PRIMARY KEY,
  nome           TEXT NOT NULL,
  telefone_e164  TEXT NOT NULL UNIQUE,
  criado_em      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ---------- CRIANCA: ancora da arvore. Chave primaria = CPF ----------
-- TEXT PRIMARY KEY (nao INTEGER) e' o que preserva zeros a esquerda: em SQLite
-- somente "INTEGER PRIMARY KEY" vira alias de rowid e sofre coercao numerica.
CREATE TABLE IF NOT EXISTS crianca (
  cpf               TEXT PRIMARY KEY
                      CHECK (length(cpf) = 11 AND cpf NOT GLOB '*[^0-9]*'),
  id_responsavel    TEXT NOT NULL REFERENCES responsavel(id),
  nome              TEXT NOT NULL,
  codigo_inscricao  TEXT NOT NULL UNIQUE,
  criado_em         TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- ---------- CONTATOS DE APOIO: ancorados na crianca (decisao 5) ----------
CREATE TABLE IF NOT EXISTS contato_apoio (
  id             TEXT PRIMARY KEY,
  cpf_crianca    TEXT NOT NULL REFERENCES crianca(cpf),
  nome           TEXT NOT NULL,
  grau_relacao   TEXT NOT NULL,
  telefone_e164  TEXT NOT NULL,
  criado_em      TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  UNIQUE (cpf_crianca, telefone_e164)
);

-- Trava de ate 2 contatos por crianca - decisao 3 ("validado no banco").
-- RAISE(ABORT) do SQLite nao interpola valores na mensagem, entao usamos um
-- codigo estavel que a aplicacao consegue distinguir da violacao de UNIQUE.
CREATE TRIGGER IF NOT EXISTS trg_max_contatos_apoio
BEFORE INSERT ON contato_apoio
FOR EACH ROW
WHEN (SELECT COUNT(*) FROM contato_apoio WHERE cpf_crianca = NEW.cpf_crianca) >= 2
BEGIN
  SELECT RAISE(ABORT, 'CRF_MAX_CONTATOS_APOIO: crianca ja possui 2 contatos de apoio cadastrados');
END;

-- ---------- ESTADO DA CONVERSA GUIADA ----------
-- Sessao controlada por RESPONSAVEL (e' o telefone dele que responde), mas
-- registra para qual CRIANCA os contatos estao sendo capturados.
CREATE TABLE IF NOT EXISTS conversa_captura (
  id              TEXT PRIMARY KEY,
  id_responsavel  TEXT NOT NULL REFERENCES responsavel(id),
  cpf_crianca     TEXT NOT NULL REFERENCES crianca(cpf),
  indice_contato  INTEGER NOT NULL CHECK (indice_contato IN (1, 2)),
  etapa           TEXT NOT NULL DEFAULT 'NOME'
                    CHECK (etapa IN ('NOME', 'PARENTESCO', 'TELEFONE', 'CONFIRMAR_PROXIMO')),
  dados_parciais  TEXT NOT NULL DEFAULT '{}' CHECK (json_valid(dados_parciais)),
  status          TEXT NOT NULL DEFAULT 'EM_ANDAMENTO'
                    CHECK (status IN ('EM_ANDAMENTO', 'CONCLUIDA')),
  criado_em       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now')),
  atualizado_em   TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

-- Uma unica sessao em andamento por responsavel: impede que uma resposta da
-- familia fique ambigua sobre a qual crianca ela se refere.
CREATE UNIQUE INDEX IF NOT EXISTS ux_captura_ativa
  ON conversa_captura (id_responsavel)
  WHERE status = 'EM_ANDAMENTO';

-- ---------- FILA (secao 8.2) ----------
-- Criancas do mesmo responsavel esperando a vez de ter os contatos capturados,
-- enquanto a sessao de outra irma/irmao ainda esta aberta.
CREATE TABLE IF NOT EXISTS captura_pendente (
  id              TEXT PRIMARY KEY,
  id_responsavel  TEXT NOT NULL REFERENCES responsavel(id),
  cpf_crianca     TEXT NOT NULL UNIQUE REFERENCES crianca(cpf),
  criado_em       TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_captura_pendente_fila
  ON captura_pendente (id_responsavel, criado_em);

-- ---------- LOG DE MENSAGENS ----------
CREATE TABLE IF NOT EXISTS mensagem (
  id                   TEXT PRIMARY KEY,
  id_responsavel       TEXT NOT NULL REFERENCES responsavel(id),
  direcao              TEXT NOT NULL CHECK (direcao IN ('ENVIADA', 'RECEBIDA')),
  conteudo             TEXT NOT NULL,
  template_usado       TEXT,
  id_mensagem_externa  TEXT,
  criado_em            TEXT NOT NULL DEFAULT (strftime('%Y-%m-%dT%H:%M:%fZ', 'now'))
);

CREATE INDEX IF NOT EXISTS idx_mensagem_responsavel
  ON mensagem (id_responsavel, criado_em);
