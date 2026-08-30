# CRF — Central de Relacionamento com a Família

**Projeto Match Perfeito — Inteligência na Inscrição de Creche**

Um protótipo que monta a rede de contatos de confiança de cada criança **no
momento da inscrição na creche**, conversando com a família pelo WhatsApp.

---

## O problema

Uma família se inscreve na fila da creche e espera meses. Quando finalmente
aparece uma vaga, a Prefeitura liga — e ninguém responde. Número trocado, celular
perdido, a mãe está no trabalho e não pode atender.

A vaga vai para o próximo da fila. E aquela família continua esperando, sem nunca
saber que a vez dela chegou.

## A ideia

**Pedir os contatos de apoio no dia da inscrição, não no dia da vaga.**

Quando a criança é inscrita, o sistema puxa conversa no WhatsApp do responsável e
pede uma ou duas pessoas de confiança — a avó, um vizinho, uma tia. Meses depois,
quando a vaga surgir, existe mais de uma porta para bater.

É como a lista de contatos de emergência da escola, só que criada no momento
certo: quando a família está engajada porque acabou de se inscrever, e não no
meio de uma urgência.

---

## Como funciona

Sem site, sem aplicativo, sem senha. A família recebe uma mensagem e responde.
E responde **um campo por vez**:

```
CRF   ▸ Olá, Maria! Aqui é a Prefeitura do Rio – Educação. Recebemos a
        inscrição de Ana Silva para creche. Precisamos de 1 ou 2 pessoas de
        confiança para avisar caso não consigamos falar com você.
        Qual o nome da primeira pessoa?

Maria ◂ Joana Souza

CRF   ▸ Qual o parentesco de Joana Souza com você? (ex.: avó, tio, vizinho)

Maria ◂ vovó

CRF   ▸ Qual o telefone de Joana Souza?

Maria ◂ (21) 98888-1234

CRF   ▸ Contato registrado! Quer cadastrar mais uma pessoa para Ana Silva?
        Responda SIM ou NÃO.
```

Se o sistema pedisse tudo de uma vez, viria *"minha sogra Joana e o vizinho
Carlos"* — e alguém teria que decifrar. Uma pergunta por vez elimina isso: o
sistema sempre sabe o que está perguntando, então sempre sabe interpretar a
resposta.

Isso exige que ele **tenha memória**. Cada mensagem chega isolada, como uma carta
solta, e o sistema precisa saber em que ponto da conversa cada família está. É a
peça central do que foi construído aqui.

---

## As regras de comportamento

**Insiste onde importa, cede onde não importa.** Se a família responde "não
lembro" no lugar do telefone, o sistema pergunta de novo — contato sem telefone
não serve para nada. Mas se ela responde "pessoa que cuida dela" no lugar do
parentesco, o sistema aceita e segue: ali, travar a conversa custa mais do que
ganha.

**Até 2 contatos por criança**, e essa regra está garantida no próprio banco de
dados — não depende de o programa estar correto.

**Os contatos são da criança, não do responsável.** Se a mesma mãe tem dois
filhos inscritos, cada um tem sua própria lista. A mesma avó pode ser contato
dos dois netos.

**Irmãos entram numa fila.** Uma família tem um só WhatsApp. Se duas conversas
rodassem ao mesmo tempo, "Joana Souza" seria ambíguo — de qual filho? Então o
segundo filho espera, e a conversa dele emenda na do primeiro
automaticamente, sem a família precisar pedir.

**Se a família para de responder, o sistema não desiste na hora.** Depois de um
dia de silêncio, manda um lembrete retomando *exatamente* a pergunta onde parou —
sem obrigar ninguém a começar de novo. Depois de três dias, encerra a conversa;
a inscrição continua valendo.

**E se a família voltar depois?** O sistema retoma o cadastro abandonado. Mas não
transforma um "oi, ainda dá tempo?" no nome da pessoa de confiança — repete a
pergunta. Registrar um contato chamado "oi" seria pior do que perguntar duas
vezes.

**O sistema recusa o que não pode aceitar:** inscrição sem o CPF da criança, CPF
inválido, número de inscrição que já é de outra criança. E fica calado quando
deve: a mesma inscrição chegando duas vezes não duplica nada nem incomoda a
família outra vez.

---

## Vendo funcionando

Requer [Python 3.12+](https://www.python.org/) e [uv](https://docs.astral.sh/uv/).

```bash
uv sync
uv run python scripts/demo.py --simples
```

A demo roda tudo sozinha, sem precisar de servidor nem banco instalado, e imprime
a história completa de duas famílias: a Maria, que responde tudo, e a Carla, que
para no meio e volta dias depois. São 9 cenários, incluindo os casos que dão
errado.

| Comando | Para quê |
|---|---|
| `uv run python scripts/demo.py --simples` | Mostrar a alguém o que o sistema faz. Lê como conversa de WhatsApp |
| `uv run python scripts/demo.py` | Depurar. Mostra o estado interno a cada passo |
| `... --simples --pausa` | Apresentar ao vivo: espera Enter entre cada mensagem |

### Rodando como servidor

```bash
uv run uvicorn app.main:app --reload
```

Sobe em `http://127.0.0.1:8000`, com uma página de testes em `/docs` onde é
possível conduzir a conversa inteira clicando, sem terminal — dá para usar como
painel improvisado numa apresentação.

---

## O que existe e o que não existe

**Existe:** cadastro do responsável e da criança a partir da inscrição, a
conversa guiada completa, a fila de irmãos, o ciclo de lembrete e desistência, e
uma consulta para inspecionar a rede de contatos de cada criança.

**Não existe, por decisão de escopo:** aviso à família de que a vaga saiu,
acionamento em cascata dos contatos, painel para a unidade escolar, e a
integração real com o WhatsApp. No lugar dela, o protótipo simula tanto a
inscrição chegando quanto as respostas da família — o que é justamente o que
permite a demo rodar inteira em segundos.

## Limitações que vale saber

- **Os lembretes precisam de um agendador.** O sistema tem a rotina que verifica
  prazos, mas alguém precisa chamá-la periodicamente. Sem isso, a conversa
  abandonada só é encerrada quando uma nova inscrição daquela família chega.
- **Um lembrete por período de silêncio**, sem escalonamento.
- **Respostas ambíguas no "quer cadastrar mais um?"** — "talvez", "acho que sim" —
  são tratadas como não.
- **Família com dois filhos cadastra os mesmos contatos duas vezes**, uma por
  criança. É consequência de os contatos serem da criança; foi aceito
  conscientemente.
- **Os webhooks não têm autenticação.** É protótipo.

---

## Documentação

| Documento | Conteúdo |
|---|---|
| [Especificação do recorte](docs/CRF%20-%20MVP%20Reduzido%20-%20Cadastro%20e%20Captura%20de%20Contatos.md) | O que foi especificado, as decisões de produto e os casos de borda |
| [Notas técnicas](docs/NOTAS-TECNICAS.md) | Estrutura do código, endpoints, modelo de dados, decisões de implementação e pontos abertos |
