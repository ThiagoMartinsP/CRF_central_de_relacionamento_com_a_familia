# CRF — Central de Relacionamento com a Família

**Projeto Match Perfeito — Inteligência na Inscrição de Creche**

Um protótipo que monta a rede de contatos de confiança de cada criança **no
momento da inscrição na creche**, conversando com a família pelo WhatsApp.

📹 **Demonstração** — o fluxo completo em execução:

https://github.com/user-attachments/assets/112c2dc4-3b99-41b3-b89d-7f41e2912048

<sub>Se o player acima não carregar, o vídeo também está versionado em
[docs/demo_CRF.mp4](docs/demo_CRF.mp4).</sub>

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

A família recebe uma mensagem e responde.
E responde **um campo por vez**:

```
CRF   ▸ Olá, Maria! Aqui é a Prefeitura do Rio – Educação. Recebemos a
        inscrição de Ana Silva para creche. Precisamos de 1 ou 2 pessoas de
        confiança para avisar caso não consigamos falar com você.
        Qual o nome da primeira pessoa?

Maria ◂ Joana Souza

CRF   ▸ Qual o parentesco de Joana Souza com a Ana Silva? (ex.: avó, tio, vizinho)

Maria ◂ Avó

CRF   ▸ Qual o telefone de Joana Souza?

Maria ◂ (21) 98888-1234

CRF   ▸ Contato registrado! Quer cadastrar mais uma pessoa para Ana Silva?
        Responda SIM ou NÃO.
```

Se o sistema pedisse tudo de uma vez, viria *"minha sogra Joana e o vizinho
Carlos"* — e alguém teria que decifrar. Uma pergunta por vez elimina isso: o
sistema sempre sabe o que está perguntando, então sempre sabe interpretar a
resposta.

---

## As regras de comportamento

**Insiste onde importa, cede onde não importa.** Se a família responde "não
lembro" no lugar do telefone, o sistema pergunta de novo — contato sem telefone
não serve para nada. Mas se ela responde "pessoa que cuida dela" no lugar do
parentesco, o sistema aceita e segue: ali, travar a conversa custa mais do que
ganha.

**Até 2 contatos adicionais por criança**.

**Os contatos são da criança, não do responsável.** Se a mesma mãe tem dois
filhos inscritos, cada um tem sua própria lista. A mesma avó pode ser contato
dos dois netos.

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

## A régua de comunicação

> Esta parte **ainda não está implementada**. É a continuação natural da ideia, e
> está descrita aqui porque sem ela o resto perde força com o tempo.

Cadastrar os contatos uma vez não basta. A fila de creche dura meses, às vezes
anos — e nesse tempo número muda, pessoa se muda, celular se perde. Uma árvore de
contatos montada no dia da inscrição e nunca mais tocada envelhece até virar uma
lista de números que não atendem mais.

A ideia é o CRF manter uma **conversa periódica** com a família — uma régua de
comunicação — só para confirmar que o contato principal continua **alcançável**.
Uma mensagem leve de vez em quando; a resposta, ou o silêncio, diz se aquele
número ainda é o caminho certo.

O efeito prático é mudar qual porta a creche bate primeiro:

- **Sem a régua:** quando a vaga aparece, a creche liga para o número que foi
  cadastrado há dois anos e torce.
- **Com a régua:** a creche liga para o contato **confirmado mais
  recentemente**. Um número que parou de responder deixa de ser a opção
  principal, e outro da árvore assume o lugar.

O objetivo é que cada criança tenha sempre, como primeira porta, alguém
**localizado e disponível** — e não apenas alguém que estava disponível no dia da
inscrição.

---

## O que existe e o que não existe

**Existe:** cadastro do responsável e da criança a partir da inscrição, a
conversa guiada completa, a fila de irmãos, o ciclo de lembrete e desistência, e
uma consulta para inspecionar a rede de contatos de cada criança.

**Não existe, por decisão de escopo:** a régua de comunicação descrita acima,
aviso à família de que a vaga saiu, acionamento em cascata dos contatos, painel
para a unidade escolar, e a integração real com o WhatsApp. No lugar dela, o
protótipo simula tanto a inscrição chegando quanto as respostas da família — o
que é justamente o que permite a demo rodar inteira em segundos.
