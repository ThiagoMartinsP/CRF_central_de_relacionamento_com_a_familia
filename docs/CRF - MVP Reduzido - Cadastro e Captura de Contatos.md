# CRF — MVP Reduzido: Cadastro e Captura de Contatos
## Especificação para Implementação

**Projeto:** Match Perfeito — Inteligência na Inscrição de Creche
**Escopo desta especificação:** apenas o recorte de captura (T0), conforme decisão de simplificação de 30/08/2026.
**Não está aqui:** convocação, cascata de acionamento, vaga, painel de unidade, score de confiabilidade, check-ins periódicos, autoatendimento. Essas peças continuam descritas em `CRF - Briefing Tecnico do Prototipo.md` e `CRF - Especificacao Funcional.md` para uma fase posterior — este documento não as substitui, apenas adia.

---

## 1. O fluxo que este documento implementa

1. **Inscrição chega no CRF.** O matricula.rio informa que uma criança foi inscrita, com o CPF da criança, o telefone do responsável e os dados básicos.
2. **CRF cria o registro e pede contatos de apoio.** Grava responsável + criança (chaveada pelo próprio CPF) no banco e inicia uma conversa guiada no WhatsApp pedindo até 2 contatos de apoio, um campo por vez.
3. **Família responde.** Cada resposta é validada e gravada. Ao fim, os contatos de apoio ficam registrados, vinculados à **criança** (ver decisão 5 abaixo — revista nesta rodada).

Não há convocação de vaga, cascata, nem painel de unidade neste recorte. O objetivo é provar a árvore de contato nascendo a partir da inscrição.

---

## 2. Decisões fechadas nesta rodada

| # | Pergunta | Decisão |
|---|---|---|
| 1 | Como a família responde ao pedido de contatos? | **Fluxo guiado, uma pergunta por vez** (nome → parentesco → telefone, campo a campo — não é parsing de texto livre). |
| 2 | Como a inscrição do matricula.rio chega no CRF? | **Endpoint HTTP simulando o webhook do matricula.rio.** Sem integração real neste protótipo. |
| 3 | Quantos contatos de apoio o protótipo aceita por criança? | **Até 2, validado no banco** (trigger, não só validação de aplicação). |
| 4 | O que fazer se o responsável do matricula.rio já existe no banco (ex.: segundo filho sendo inscrito)? | **Cria a nova criança e sempre reabre a captura de contatos para ela** — resolvido de forma direta pela decisão 5: como a árvore agora é por criança, não há ambiguidade de "já tem os 2 contatos", porque cada criança começa com zero. |
| 5 | Em que entidade a árvore de contato é ancorada, e qual é a chave primária da criança? | **Ancorada na própria criança. A chave primária de `crianca` é o CPF dela**, não mais um UUID substituto ligado ao responsável. Decisão revista nesta rodada — ver 2.1 para o que isso substitui e o que isso reabre. |

### 2.1 Como as críticas da rodada anterior entram aqui

- **Ancoragem — revista.** As rodadas anteriores fixavam a árvore no responsável, justamente para evitar que dois filhos do mesmo responsável tivessem árvores de contato duplicadas e envelhecendo em separado. Esta decisão inverte isso: a árvore passa a ser por criança. Consequência aceita conscientemente: se o mesmo responsável tiver dois filhos inscritos, a família será convidada a cadastrar os contatos de apoio **duas vezes**, uma por criança, mesmo que sejam as mesmas pessoas (ver seção 8.1). Isso é o trade-off direto da decisão 5, documentado para não ser redescoberto como bug mais tarde.
- **CPF do responsável (crítica antiga) — superada.** A lacuna anterior era a falta de lugar para guardar o CPF do responsável. Deixou de ser relevante porque agora é o CPF **da criança** que vira a chave primária, e essa é uma peça de dado diferente. Fica um requisito em aberto no lugar dela: confirmar que o matricula.rio de fato coleta e valida o CPF da criança (não só o do responsável) no ato da inscrição — ver seção 11, item 1.
- **CPF ausente em parte da base (crítica antiga) — parcialmente endereçada, não eliminada.** O padrão dos últimos anos é a criança sair da maternidade com CPF vinculado à certidão de nascimento, o que reduz bastante o caso de ausência. Mas "reduz bastante" não é "elimina": crianças nascidas fora do Brasil, registro tardio, ou nascidas em cartórios que ainda não tinham o processo consolidado continuam sem CPF. Como o campo agora é chave primária `NOT NULL`, essas crianças simplesmente não entram no banco neste desenho — não há fallback. Ver seção 8.3.
- **Estado de conversa** — continua sendo resolvido pela tabela `conversa_captura`, mas agora com uma peça a mais: como a sessão guiada precisa ser identificada por número de telefone (é o WhatsApp do responsável que responde, não a criança), e a árvore agora é por criança, é preciso separar "de quem é o número que está respondendo" de "para qual criança os contatos estão sendo gravados". Ver seção 3 e 5 — isso também é o que resolve a fila da seção 8.2.
- **Worker/cascata/estado de convocação** — segue fora de escopo, sem mudança em relação à versão anterior deste documento.

---

## 3. Modelo de dados

```sql
-- ---------- ENUMS ----------
CREATE TYPE etapa_captura   AS ENUM ('NOME', 'PARENTESCO', 'TELEFONE', 'CONFIRMAR_PROXIMO');
CREATE TYPE status_captura  AS ENUM ('EM_ANDAMENTO', 'CONCLUIDA');
CREATE TYPE direcao_msg     AS ENUM ('ENVIADA', 'RECEBIDA');

-- ---------- RESPONSÁVEL: continua existindo como canal de mensageria (telefone),
-- mas deixou de ser a âncora da árvore de contato ----------
CREATE TABLE responsavel (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  nome           TEXT NOT NULL,
  telefone_e164  TEXT UNIQUE NOT NULL,   -- número recebido do matricula.rio
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- CRIANÇA: agora é a âncora da árvore. Chave primária = CPF ----------
CREATE TABLE crianca (
  cpf               CHAR(11) PRIMARY KEY CHECK (cpf ~ '^\d{11}$'),  -- sem pontuação, com zeros à esquerda
  id_responsavel    UUID NOT NULL REFERENCES responsavel(id),
  nome              TEXT NOT NULL,
  codigo_inscricao  TEXT UNIQUE NOT NULL,  -- referência da inscrição no matricula.rio, mantida à parte do CPF
  criado_em         TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- ---------- CONTATOS DE APOIO: ancorados na criança (decisão 5) ----------
CREATE TABLE contato_apoio (
  id            UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  cpf_crianca   CHAR(11) NOT NULL REFERENCES crianca(cpf),
  nome          TEXT NOT NULL,
  grau_relacao  TEXT NOT NULL,          -- texto livre normalizado; ver seção 7
  telefone_e164 TEXT NOT NULL,
  criado_em     TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (cpf_crianca, telefone_e164)
);

-- trava de até 2 contatos por criança — decisão 3 ("validado no banco")
CREATE OR REPLACE FUNCTION fn_valida_max_contatos_apoio()
RETURNS TRIGGER AS $$
BEGIN
  IF (SELECT COUNT(*) FROM contato_apoio WHERE cpf_crianca = NEW.cpf_crianca) >= 2 THEN
    RAISE EXCEPTION 'criança % já possui 2 contatos de apoio cadastrados', NEW.cpf_crianca;
  END IF;
  RETURN NEW;
END;
$$ LANGUAGE plpgsql;

CREATE TRIGGER trg_max_contatos_apoio
BEFORE INSERT ON contato_apoio
FOR EACH ROW EXECUTE FUNCTION fn_valida_max_contatos_apoio();

-- ---------- ESTADO DA CONVERSA GUIADA ----------
-- a sessão é controlada por RESPONSÁVEL (só uma conversa aberta por número de
-- telefone por vez — é ele quem responde no WhatsApp), mas registra para qual
-- CRIANÇA os contatos estão sendo capturados nesta sessão.
CREATE TABLE conversa_captura (
  id               UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_responsavel   UUID NOT NULL REFERENCES responsavel(id),
  cpf_crianca      CHAR(11) NOT NULL REFERENCES crianca(cpf),
  indice_contato   SMALLINT NOT NULL CHECK (indice_contato IN (1, 2)),
  etapa            etapa_captura NOT NULL DEFAULT 'NOME',
  dados_parciais   JSONB NOT NULL DEFAULT '{}',
  status           status_captura NOT NULL DEFAULT 'EM_ANDAMENTO',
  criado_em        TIMESTAMPTZ NOT NULL DEFAULT now(),
  atualizado_em    TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- só uma sessão em andamento por responsável (telefone) por vez — impede que uma
-- resposta da família fique ambígua sobre a qual criança ela se refere.
CREATE UNIQUE INDEX ux_captura_ativa ON conversa_captura (id_responsavel)
  WHERE status = 'EM_ANDAMENTO';

-- ---------- FILA: crianças do mesmo responsável esperando a vez de ter os
-- contatos capturados, enquanto a sessão de outra irmã/irmão ainda está aberta ----------
CREATE TABLE captura_pendente (
  id             UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_responsavel UUID NOT NULL REFERENCES responsavel(id),
  cpf_crianca    CHAR(11) NOT NULL REFERENCES crianca(cpf),
  criado_em      TIMESTAMPTZ NOT NULL DEFAULT now(),
  UNIQUE (cpf_crianca)
);

-- ---------- LOG DE MENSAGENS ----------
CREATE TABLE mensagem (
  id                    UUID PRIMARY KEY DEFAULT gen_random_uuid(),
  id_responsavel        UUID NOT NULL REFERENCES responsavel(id),
  direcao               direcao_msg NOT NULL,
  conteudo              TEXT NOT NULL,
  template_usado        TEXT,             -- ex.: 'M1_BOAS_VINDAS_PEDE_CONTATO', null se resposta livre
  id_mensagem_externa   TEXT,             -- id retornado pelo provedor de WhatsApp
  criado_em             TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX idx_mensagem_responsavel ON mensagem (id_responsavel, criado_em);
```

---

## 4. Endpoints

### 4.1 `POST /webhooks/matricula-rio` — simula o passo 1

Corpo esperado:

```json
{
  "codigo_inscricao": "INSC-2026-000123",
  "crianca_cpf": "12345678901",
  "crianca_nome": "Ana Silva",
  "responsavel_nome": "Maria Silva",
  "responsavel_telefone": "+5521999990001"
}
```

`crianca_cpf` é obrigatório e vira a chave primária de `crianca`. Se o matricula.rio não enviar esse campo (ver seção 8.3), o endpoint rejeita a inscrição com erro — não há criação parcial.

Lógica: descrita na seção 5.

### 4.2 `POST /webhooks/whatsapp/inbound` — simula o passo 3

```json
{
  "telefone_e164": "+5521999990001",
  "texto": "Joana"
}
```

Lógica: descrita na seção 6.

### 4.3 `GET /criancas/:cpf` — consulta de depuração

Retorna a criança, o responsável vinculado e os contatos de apoio já confirmados. Serve para inspecionar o estado da árvore durante o desenvolvimento e a demo; não é o painel final.

---

## 5. Regra de disparo (o que acontece quando a inscrição chega)

```
ao receber POST /webhooks/matricula-rio:
    se payload.crianca_cpf ausente ou formato inválido:
        rejeitar com erro 422 (ver seção 8.3 — sem CPF, sem cadastro)

    responsavel = upsert_responsavel(telefone, nome)
    crianca = upsert_crianca(cpf, responsavel.id, nome_crianca, codigo_inscricao)
    # upsert por CPF: reenvio da mesma inscrição não duplica nem reabre captura

    total_contatos = count(contato_apoio WHERE cpf_crianca = crianca.cpf)
    ja_capturando_esta_crianca = existe conversa_captura
        WHERE cpf_crianca = crianca.cpf AND status = 'EM_ANDAMENTO'
    responsavel_ocupado = existe conversa_captura
        WHERE id_responsavel = responsavel.id AND status = 'EM_ANDAMENTO'

    se total_contatos >= 2 ou ja_capturando_esta_crianca:
        continuar sem ação adicional

    senao se responsavel_ocupado:
        # o mesmo responsável já está no meio da captura de outra criança —
        # enfileira esta e não manda mensagem agora (ver seção 8.2)
        INSERT captura_pendente (id_responsavel, cpf_crianca)

    senao:
        enviar(responsavel, template = 'M1_BOAS_VINDAS_PEDE_CONTATO', contexto = crianca)
        cria conversa_captura(
            id_responsavel = responsavel.id,
            cpf_crianca = crianca.cpf,
            indice_contato = 1,
            etapa = 'NOME'
        )
```

---

## 6. Máquina de estados da captura guiada

Cada contato de apoio é capturado em 3 campos sequenciais. `etapa_captura` avança um passo por resposta válida.

```
NOME  ──(resposta válida)──►  PARENTESCO  ──(resposta válida)──►  TELEFONE
                                                                       │
                                                          (telefone válido)
                                                                       ▼
                                                 grava em contato_apoio
                                                 (cpf_crianca = sessao.cpf_crianca)
                                                                       │
                                                                       ▼
                                                          CONFIRMAR_PROXIMO
                                                        (pergunta: "quer
                                                         cadastrar mais um
                                                         contato para esta
                                                         criança?")
                                          ┌────────────────────┴────────────────────┐
                                     responde SIM                             responde NÃO
                                   (e indice=1)                              ou indice=2
                                          ▼                                          ▼
                              abre nova sessão                            encerrar_sessao()
                              indice_contato=2                            (ver 6.2 — fecha e
                              etapa=NOME                                   destrava a fila)
```

### 6.1 Lógica do webhook inbound

```
ao receber POST /webhooks/whatsapp/inbound (telefone, texto):
    responsavel = busca_responsavel_por_telefone(telefone)
    se responsavel não existe:
        ignora (número não reconhecido — fora de escopo do MVP)

    sessao = select conversa_captura
             WHERE id_responsavel = responsavel.id AND status = 'EM_ANDAMENTO'
    se sessao não existe:
        ignora (não há pergunta em aberto para este número)

    grava mensagem(direcao='RECEBIDA', conteudo=texto)

    caso sessao.etapa:
        NOME:
            se texto vazio: reenviar pergunta de nome com aviso de erro; não avança
            senão: sessao.dados_parciais.nome = texto
                    sessao.etapa = PARENTESCO
                    enviar pergunta de parentesco

        PARENTESCO:
            grau = normaliza_grau_relacao(texto)
            sessao.dados_parciais.grau_relacao = grau
            sessao.etapa = TELEFONE
            enviar pergunta de telefone

        TELEFONE:
            se não valida_e164_brasil(texto):
                reenviar pergunta de telefone com aviso de erro; não avança
            senão:
                INSERT INTO contato_apoio (
                    cpf_crianca, nome, grau_relacao, telefone_e164
                ) VALUES (
                    sessao.cpf_crianca,
                    sessao.dados_parciais.nome,
                    sessao.dados_parciais.grau_relacao,
                    normaliza_e164(texto)
                )
                # trigger trg_max_contatos_apoio garante o limite de 2
                sessao.etapa = CONFIRMAR_PROXIMO
                se sessao.indice_contato == 1:
                    enviar "Quer cadastrar mais um contato de apoio para [CRIANCA]? (SIM/NÃO)"
                senão:
                    encerrar_sessao(sessao)

        CONFIRMAR_PROXIMO:
            se texto normaliza para SIM e sessao.indice_contato == 1:
                sessao.status = CONCLUIDA
                cria nova conversa_captura(
                    id_responsavel = responsavel.id,
                    cpf_crianca = sessao.cpf_crianca,
                    indice_contato = 2,
                    etapa = NOME
                )
                enviar pergunta de nome (segundo contato)
            senão:
                encerrar_sessao(sessao)
```

### 6.2 Rotina `encerrar_sessao` (destrava a fila da seção 8.2)

```
rotina encerrar_sessao(sessao):
    sessao.status = CONCLUIDA
    enviar(sessao.id_responsavel, template = 'M1_ENCERRAMENTO', contexto = sessao.cpf_crianca)

    proxima = select captura_pendente
              WHERE id_responsavel = sessao.id_responsavel
              ORDER BY criado_em LIMIT 1

    se proxima existe:
        DELETE captura_pendente WHERE id = proxima.id
        enviar(sessao.id_responsavel,
               template = 'M1_PEDE_CONTATO_PROXIMA_CRIANCA',
               contexto = proxima.cpf_crianca)
        cria conversa_captura(
            id_responsavel = sessao.id_responsavel,
            cpf_crianca = proxima.cpf_crianca,
            indice_contato = 1,
            etapa = 'NOME'
        )
```

---

## 7. Validações

- **CPF (`valida_cpf`):** formato — 11 dígitos numéricos, sem pontuação, preservando zeros à esquerda (armazenar como `CHAR(11)`/`TEXT`, nunca como número — é o erro mais comum e mais silencioso nesse tipo de campo). O `CHECK` do banco (`cpf ~ '^\d{11}$'`) garante só o formato; a validação do dígito verificador (algoritmo oficial da Receita) fica na aplicação, não no banco, porque dado sintético de demo não precisa necessariamente passar nesse cálculo — mas vale gerar os CPFs de teste já com dígito verificador válido, para não mascarar um bug de validação que só apareceria com CPF real.
- **Telefone (`valida_e164_brasil`):** aceita formatos comuns de entrada (`(21) 99999-0001`, `21999990001`, `+5521999990001`) e normaliza para `+55DDD9XXXXXXXX`.
- **Parentesco (`normaliza_grau_relacao`):** não trava em enum fechado no banco (o campo é `TEXT`), mas a aplicação tenta casar a resposta contra uma lista de sinônimos conhecida (mãe, pai, avó, avô, tio, tia, irmão, irmã, vizinho, amigo) e grava o texto original se não reconhecer.
- **Nome:** apenas não-vazio neste MVP.

---

## 8. Casos de borda documentados

### 8.1 Duas crianças do mesmo responsável

Consequência direta da decisão 5 (ancoragem por criança): cada criança começa a árvore do zero, mesmo que o responsável seja o mesmo e os contatos de apoio sejam as mesmas pessoas. A família responde ao fluxo guiado uma vez por criança. Isso é aceito como trade-off desta rodada, não é um bug — mas é o tipo de coisa que vale confirmar com quem vai usar o sistema antes de escalar, porque pode gerar fadiga em famílias com mais de um filho na fila de creche ao mesmo tempo.

### 8.2 Duas crianças do mesmo responsável, capturas simultâneas

Tratado pela fila `captura_pendente` + índice único `ux_captura_ativa`: quando a segunda inscrição chega enquanto a primeira captura ainda está aberta, a criança nova é criada normalmente, mas o convite só é enviado quando a sessão da primeira criança fecha (rotina `encerrar_sessao`, seção 6.2). Isso evita a ambiguidade de uma resposta do responsável não ter como indicar a qual criança ela se refere.

### 8.3 Criança sem CPF na inscrição

Não tratado neste MVP: como `crianca.cpf` é `NOT NULL PRIMARY KEY`, uma inscrição sem CPF é rejeitada no endpoint (erro 422), e a criança não entra no banco. Isso é uma lacuna real, não hipotética — casos que ainda podem não ter CPF incluem registro tardio, nascimento fora do Brasil, ou cartórios com adesão mais recente à emissão automática. Ver seção 11, item 2, para a decisão que falta tomar aqui.

### 8.4 Família nunca responde

Sem tratamento neste MVP (sem cascata, sem lembrete, sem expiração). A sessão fica `EM_ANDAMENTO` indefinidamente — aceitável para o protótipo.

> **Resolvido depois desta especificação.** Este caso foi implementado: um lembrete após 24h de silêncio da família, expiração após 72h, e a expiração destrava a fila `captura_pendente`. O motivo de não ter ficado como "aceitável para o protótipo" é que a consequência não era só a família perdida: como só existe uma sessão ativa por responsável, uma conversa abandonada bloqueava permanentemente todas as outras crianças daquele responsável. Ver a seção "Expiração de sessão" no `README.md`.

### 8.5 Resposta fora de formato (telefone inválido, etc.)

O webhook reenvia a mesma pergunta com uma mensagem de erro e não avança de etapa. Não há limite de tentativas neste MVP.

---

## 9. Mensagens (templates)

| Template | Momento | Texto de referência |
|---|---|---|
| `M1_BOAS_VINDAS_PEDE_CONTATO` | Inscrição nova, criança sem sessão ativa nem 2 contatos | "Olá, [NOME]! Aqui é a Prefeitura do Rio – Educação. Recebemos a inscrição de [CRIANCA] para creche. Precisamos de 1 ou 2 pessoas de confiança para avisar caso não consigamos falar com você. Qual o nome da primeira pessoa?" |
| `M1_PEDE_PARENTESCO` | Após nome válido | "Qual o parentesco de [NOME_CONTATO] com você? (ex.: avó, tio, vizinho)" |
| `M1_PEDE_TELEFONE` | Após parentesco válido | "Qual o telefone de [NOME_CONTATO]?" |
| `M1_PERGUNTA_SEGUNDO` | Após 1º contato gravado | "Contato registrado! Quer cadastrar mais uma pessoa para [CRIANCA]? Responda SIM ou NÃO." |
| `M1_ENCERRAMENTO` | Fim da captura para esta criança (2º contato ou resposta NÃO) | "Prontinho! Os contatos de apoio de [CRIANCA] estão registrados. Vamos avisar por aqui assim que surgir uma vaga." |
| `M1_PEDE_CONTATO_PROXIMA_CRIANCA` | Sessão anterior fechou e há outra criança do mesmo responsável na fila (8.2) | "Agora vamos cadastrar os contatos de apoio de [CRIANCA_2]. Qual o nome da primeira pessoa?" |
| `ERRO_TELEFONE_INVALIDO` | Telefone fora de formato | "Não consegui entender esse número. Pode mandar de novo? (ex.: (21) 99999-0001)" |

---

## 10. Fora de escopo (deliberadamente, herdado do desenho completo)

Convocação de vaga e sua máquina de estados; cascata de acionamento (titular → corresponsável → apoio → fallback); tabela `vaga`; painel da unidade escolar e as três filas; score de confiabilidade do nó; check-ins periódicos (M2); autoatendimento; tabela `identificador` (DNV/NIS) para os casos sem CPF; qualquer integração real com Cloud API/Evolution API.

---

## 11. Pontos a confirmar antes de codar

1. **O matricula.rio de fato coleta e valida o CPF da criança no ato da inscrição** — não só o do responsável. Se essa validação hoje só existe para o responsável (como o desenho anterior descrevia), o payload da seção 4.1 não tem de onde vir, e isso precisa ser resolvido com a SME antes de fixar `crianca.cpf` como chave primária em produção. Para o protótipo com dado sintético isso não bloqueia nada — basta gerar CPFs de teste — mas é o requisito que decide se este desenho sobrevive fora do hackathon.
2. **O que fazer com uma criança sem CPF (seção 8.3)** — hoje ela simplesmente não entra no banco. Se isso não for aceitável (mesmo que raro), a alternativa é manter `crianca.cpf` como coluna `UNIQUE` em vez de chave primária, com um UUID substituto por baixo — o que preserva a maior parte do ganho desta decisão (CPF continua garantindo deduplicação e é o identificador natural para consulta) sem excluir do sistema a criança que, por exceção, ainda não tem CPF.
3. **Fadiga de recadastro entre irmãos (8.1)** — confirmar que pedir os mesmos contatos de apoio duas vezes para famílias com dois filhos na fila é aceitável, ou se vale a pena um atalho futuro (ex.: "usar os mesmos contatos de [CRIANCA_1]? SIM/NÃO") — fora de escopo deste MVP, mas fica registrado como próxima iteração natural.

---

## Notas de implementação

O estado da implementação, as traduções de PostgreSQL para SQLite e as decisões que este documento deixou abertas estão registradas no `README.md` na raiz do repositório.
