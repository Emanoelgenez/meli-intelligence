# G36 — correção candidata do histórico público no Streamlit Cloud

Atualizado em 15/10/2026. **Candidato local; publicação e homologação no Cloud pendentes.**
Worktree: `C:\Projetos\invest-g36`. Branch: `fix/g36-public-demo-cloud`.
Nenhum push, deploy, reinício ou alteração do aplicativo online foi realizado.

## A. Causa e grau de evidência

### Comprovado em reprodução

A instalação não editável (`requirements.txt` com `.`) copia o pacote para
`site-packages`. Atualizar somente o checkout não atualiza essa cópia. O código
original continua exigindo contrato `1`, enquanto o manifesto G31 declara `2`.
O resultado é:

```
ValueError: Public manifest does not match the approved release contract.
```

A validação acontece antes da leitura dos Parquet. `health.py` captura ValueError
e converte a falha em indisponibilidade genérica. Cada dataset valida o bundle
completo; portanto financeiro e operacional ficam INVALID simultaneamente.
A falha foi reproduzida com uv e pip, com o mesmo carregador, modo público e
arquivos válidos. Também foi reproduzida em um processo Streamlit persistente.
Isso separa a incompatibilidade de código/contrato de um problema de apresentação
ou de corrupção do Parquet.

O G31 não mudou requirements.txt, pyproject.toml ou o entrypoint. A versão do
pacote permaneceu 0.1.0. Os testes anteriores usavam `pythonpath = ["src"]` no
pytest, e o teste de checkout limpo injetava PYTHONPATH=src no subprocesso:
eles não exercitavam uma cópia antiga do pacote instalada antes da atualização.

### Evidência de produção fornecida pelo usuário

Os registros abaixo são o resumo dos logs informado pelo usuário, não uma coleta
administrativa direta ou uma cópia integral dos logs realizada nesta investigação.
Em 13/10/2026:

| UTC | São Paulo | Registro informado |
|---|---|---|
| 18:29 | 15:29 | Instalação inicial por uv, requirements `.`; meli-intelligence 0.1.0 a partir de `/mount/src/meli-intelligence` |
| 18:39 | 15:39 | Atualização G31; Processing dependencies / Processed dependencies / Updated app; sem nova instalação explícita do pacote |
| 18:44 | 15:44 | Rollback; mesma sequência, sem instalação explícita |

Python 3.12.15, Streamlit 1.59.1, pandas 3.0.6 e PyArrow 24.0.0 foram informados.
Os logs não mostram diretamente o ValueError do contrato nem o `__file__` do
módulo carregado no incidente.

**Inferência histórica:** a permanência do pacote antigo em site-packages é a
explicação sustentada pela reprodução, pela ausência de reinstalação explícita,
pelo requirements inalterado e pelo sucesso imediato do rollback. Não se afirma
ter observado diretamente o módulo/contrato que o processo Cloud importou naquele
instante. A mensagem “Processed dependencies” isoladamente não prova reinstalação.

Os erros ASGI de arquivos estáticos foram mantidos separados. Não são necessários
para reproduzir a perda dos indicadores: o teste reproduz a rejeição pelo carregador
sem carregar assets de frontend. Os trechos fornecidos não permitem diagnosticar
esses erros nem provar que não tenham outro impacto; nenhuma correção ASGI foi feita.

## B. Solução mínima

`requirements.txt` passa de `.` para `-e .`. Setuptools cria uma instalação editável
que resolve os módulos no `src` do checkout. O mecanismo foi instalado de fato por
uv e pip; não houve manipulação de PYTHONPATH nem mudança de sys.path da aplicação.
A origem dos imports foi conferida com `public_demo.__file__` em intérpretes novos.
O teste de sessão persistente também registra a origem e o PID antes/depois.

Não se removeu nem flexibilizou a validação do contrato. O teste ainda corrompe
propositalmente uma cópia temporária do manifesto e exige sua rejeição.

A documentação primária descreve a instalação editável suportada pelo uv:
https://docs.astral.sh/uv/pip/packages/
O Community Cloud processa requirements e detecta alterações de dependências:
https://docs.streamlit.io/deploy/streamlit-community-cloud/deploy-your-app/app-dependencies
https://docs.streamlit.io/deploy/streamlit-community-cloud/manage-your-app/upgrade-streamlit
Esses documentos corroboram o mecanismo; a aprovação local deriva dos testes reais.

Limites: mudanças em dependências, metadados de build ou layout de pacotes ainda
exigem reinstalação. Editável não promete atualizar objetos já importados em qualquer
processo arbitrário. Foi verificado o ciclo de recarga do Streamlit, com watcher
polling e runOnSave, sem reiniciar o servidor. O serviço privado de implantação do
Cloud e sua configuração de watcher ainda precisam da homologação da Etapa A.

### Diferenças em relação ao G31

- requirements.txt: instalação editável, única mudança de runtime adicional ao G31.
- `.gitattributes`: LF no gerador, preservando o hash exato registrado no manifesto
  em Windows e Linux. Não normaliza ou ignora hashes dos dados.
- `test_public_demo_bundle.py`: determinismo de escrita comparado dentro da mesma
  versão de PyArrow; round-trip exige igualdade de tabela e metadados. PyArrow 24
  regrava bytes diferentes de PyArrow 25, apesar de ler os mesmos dados. Os hashes
  dos arquivos versionados continuam verificados integralmente pelo manifesto.
- `tests/deployment/`: comparação real normal/editável/candidato e migração em duas
  etapas, fixtures de sessão Streamlit, constraints das versões Cloud e instruções.
- `.gitignore`: exclui `.g36-evidence/`, que contém ambientes e diagnósticos locais.
- Este relatório.

Os arquivos de `src`, o gerador e os três arquivos do bundle são idênticos ao G31
no conteúdo Git. Não foram reconstruídos Parquet nem inventados dados. O manifesto
original do G31 foi preservado; nenhuma alteração de checksum foi necessária.

## C. Validação

### Ambiente representativo

Ubuntu 24.04 via WSL, Python **3.12.15**, Streamlit **1.59.1**, pandas **3.0.6** e
PyArrow **24.0.0**. Os quatro números conhecidos dos logs foram reproduzidos.
Também usados: DuckDB 1.5.6, uv 0.13.0 e setuptools 84.0.0. As versões destes
últimos no incidente não foram fornecidas; não se afirma reproduzir todo o lockfile
do Cloud. As dependências resolvidas constam dos arquivos locais de evidência.
O WSL utiliza parte dos arquivos em volume Windows; o Cloud não foi reiniciado.

Os testes de instalação criam venvs descartáveis e compartilham somente diretórios
de dependências previamente preparados. O pacote de aplicação é instalado em cada
venv; não é simulado. Os probes usam `python -I`, sem PYTHONPATH. O teste da suíte
unitária final usa `-o pythonpath=` após instalar o candidato de fato.

### Resultados consolidados

| Verificação | Resultado |
|---|---|
| Suíte Windows anterior à retomada | 728 passed; não repetida |
| Suíte unitária completa Linux, Python e três bibliotecas Cloud exatos, pacote instalado | **728 passed em 118,63 s** |
| Dois testes Windows alterados para portabilidade PyArrow | **2 passed** |
| Regressão candidata com requirements `.` antes da correção | Falhou como esperado: import de site-packages, contrato 1, datasets INVALID |
| Normal uv e pip após atualizar checkout, sem reinstalar | Falha original reproduzida; controles negativos aprovados |
| Editável uv e pip, e candidato pip, após atualização sem reinstalar | **3 passed**, com KPIs, gráficos e YoY |
| Sessão persistente normal uv | Contrato antigo rejeita manifesto novo no mesmo PID |
| Migração real Etapa A uv e pip | **2 passed em 308,42 s**; normal → editável conserva contrato 1 e 30/20; quatro páginas disponíveis antes de ampliar |
| Sessão persistente após migração uv e atualização G31 | Contrato 2, import de checkout/src, 511/55 no mesmo PID |
| Candidato uv com AppTest de 90 s | **1 passed, 7 deselected em 106,93 s**; contrato 2, 511/55, quatro páginas e YoY; servidor persistente PID 4649 |
| Ruff e formatação no escopo Python alterado | Aprovados na verificação de escopo |
| `git diff --check` | Aprovado |

A matriz é executada em partes para não repetir casos aprovados. Há oito casos:
normal, editável, candidato real e migração, cada um com uv e pip. A migração começa
com a instalação normal, processa o requirements editável mantendo o bundle original
e só depois atualiza o checkout para G31 sem nova instalação.

Durante o desenvolvimento da fixture, foram corrigidos: o nome do elemento de
gráfico do AppTest 1.59.1, a codificação de três rótulos de navegação e o ciclo de
vida do cliente WebSocket. Houve timeout de bootstrap sem qualquer JSON recebido;
a janela do smoke foi ampliada para 90 s e pings locais foram desativados. A condição
de sucesso continua exigindo o contrato e os dados esperados. Tentativas com falhas
ou interrompidas foram preservadas nos logs e não contam como aprovação.

O Ruff global já havia registrado 1665 apontamentos preexistentes e um panic interno
na formatação global com Ruff 0.17.0. Não se declara a árvore inteira limpa nem se
fez reformatação de escopo amplo. A verificação final cobre todos os Python
alterados pelo G31/G36.

### Dados e apresentação

| Indicador | Observações | Cobertura | YoY 2026Q2 |
|---|---:|---|---:|
| Receita | 33 | 2016Q1–2026Q2, com lacunas | 49,764359% |
| GMV | 11 | 2023Q4–2026Q2 | 43,701665% |
| TPV | 11 | 2023Q4–2026Q2 | 56,267608% |
| MAU | 11 | 2023Q4–2026Q2 | não exigido |

Receita continua sem 2025Q4; não houve derivação anual/YTD, interpolação ou backfill.
Fluxos continuam QUARTER; saldos e MAU continuam INSTANT. Unidades, fontes e linhagem
não mudaram. Testes de schema, proveniência, allowlist e rejeição de alterações
continuam na suíte.

AppTest instalado verificou: Visão geral 3 KPIs/3 gráficos, Financeiro 4/1, Comércio
3/1 e Serviços financeiros 2/1, sem exceções. Esses testes verificam os elementos
gerados pelo Streamlit; não substituem a inspeção visual do frontend após deploy.

### Integridade

| Parquet | Registros | SHA-256 |
|---|---:|---|
| financial_facts | 511 | a0ee1813c5ed12b9b0e30bfd358d73adc86b7da899c0eacecfab02e52f1aba99 |
| operational_kpis | 55 | 71ad07f47b9b52f10151ef40b63d8b5969a4119154cfa03b737a766047302ce6 |

Ambos coincidem com o manifesto e com os blobs de 0f31b5e. O gerador em LF mantém
`f5625fbf1eeaa180fd00a9102f401b8cc917fdc013e1fa90cd485159af454500`.
Não há dados Silver/Gold privados, mercado licenciado ou credenciais adicionados.
As fixtures copiam apenas src, demo_data, entrypoint e arquivos de empacotamento.

### Evidências e reprodução

Em `.g36-evidence/`, ignorado pelo Git:
- `resumed-versions.txt`, `cloud-exact-freeze.txt`: ambiente e dependências.
- `final-before.txt`: teste que falha com `.` antes da correção.
- `final-after.txt`: rodada com controle pip aprovado e falhas da fixture antiga;
  não deve ser usada como aprovação integral.
- `final-positive.txt`: editável uv/pip e candidato pip aprovados.
- `final-live.txt`: controle persistente normal aprovado; timeout candidato anterior.
- `candidate-uv-final.txt`: tentativa anterior com timeout; não conta como aprovação.
- `candidate-uv-accepted.txt`: candidato uv aprovado após limite AppTest de 90 s.
- `stage-a-migration.txt`: migração normal → editável com bundle original e etapa B.
- `final-unit.txt`: 728 testes Linux.
- `parquet-version.txt`: falha original dos testes de reserialização no PyArrow 24.
- `final-integrity.json`: comparação com manifesto e blobs Git.

Instruções reproduzíveis: `tests/deployment/README.md`. No WSL deste worktree Windows,
foi necessário GIT_DIR apenas para ler os objetos Git do baseline; não se alterou a
configuração Git do repositório principal. A execução não requer dados privados.

## D. Checkpoints e revisão

**Etapa A: `41221dc86d9d4dbbc953a4b9d2c898c09c2eaa31`.**
Contém somente `requirements.txt`: `.` → `-e .`. Código, manifesto e Parquet são os
de 0edc3da, com 30/20 registros. É um checkpoint independente para homologação.

**Etapa B: segundo commit da branch `fix/g36-public-demo-cloud`, após A.**
Restaura os 14 arquivos do G31 e acrescenta os testes, portabilidade e documentação
do G36. O SHA final é apresentado na entrega. Não publicar A e B juntos.

Comandos de revisão, sem escrita no remoto:

```powershell
git -C C:\Projetos\invest-g36 show --stat 41221dc
git -C C:\Projetos\invest-g36 diff 0edc3da 41221dc -- requirements.txt demo_data
git -C C:\Projetos\invest-g36 diff --stat 41221dc fix/g36-public-demo-cloud
git -C C:\Projetos\invest-g36 diff 41221dc fix/g36-public-demo-cloud -- tests/deployment
git -C C:\Projetos\invest-g36 diff 0f31b5e fix/g36-public-demo-cloud -- src demo_data scripts/build_public_demo.py
git -C C:\Projetos\invest-g36 status --short
```

O último diff deve permanecer vazio para código analítico e dados auditados.

## E. Plano de publicação e rollback — não executado

A consulta remota da investigação anterior encontrou apenas `refs/heads/main` em
0edc3da; `deploy/streamlit-mvp` era uma branch local. Confirmar o alvo efetivamente
configurado no aplicativo antes de qualquer publicação. A restrição de não alterar
origin/main permanece: estes checkpoints não autorizam push para ela.

1. Revisar A e aprovar explicitamente o alvo de publicação. Publicar **somente A**
   por um procedimento aprovado, sem levar o HEAD B junto.
2. Conferir logs de processamento: o pacote deve ser reinstalado como editável.
   Registrar versão Python/dependências e origem do módulo quando disponível.
   Se houver mudança inesperada de dependências, revisar antes de continuar.
3. Validar no Cloud contrato 1, 30/20, quatro páginas com KPIs/gráficos, modo público,
   ausência de fallback privado e ausência de erros novos. Não usar o health endpoint
   isoladamente como prova de execução das páginas.
4. **Parar e obter aprovação da Etapa A.** Só então considerar a publicação isolada B.
5. Após B, exigir contrato 2, 511/55, cobertura 33/11/11/11, YoY em 2026Q2, lacuna
   2025Q4 preservada e quatro páginas disponíveis. Inspecionar frontend e logs.

Rollback de B: reverter somente o commit B no alvo aprovado, conservando A e
restaurando o bundle original 30/20. Assim, a instalação continua editável e acompanha
o código revertido. Rollback de A: revertê-lo com o bundle original ainda presente,
permitindo reinstalação normal. Não usar reset, force push ou recriar o aplicativo.
Toda ação remota depende de aprovação posterior; nenhuma foi executada.

A validação local não equivale a homologação Cloud. O incidente histórico é explicado
por uma incompatibilidade reproduzida e fortemente corroborada, mas seu import
histórico não foi observado diretamente. **G36 permanece aguardando revisão e
aprovação; não se declara o deploy concluído.**

## F. Fechamento da retomada de 15/10/2026

Os oito casos distintos da matriz de deployment foram aprovados em execuções
segmentadas: normal uv/pip (controles negativos), editável uv/pip, candidato uv/pip
e migração uv/pip. Não se apresenta isso como uma única execução de oito casos.
O teste candidato falhou com requirements `.` e passou com `-e .`; os controles
negativos continuam exigindo a falha original. Nenhuma asserção foi removida.

O último comando interrompido já havia deixado salvo o resultado aprovado em
`candidate-uv-accepted.txt`. Por isso ele não foi repetido nesta retomada.
O AppTest passou com `default_timeout=90`, incluindo disponibilidade, gráficos,
contratos e YoY. Os 106,93 s são a duração do caso inteiro (instalação, servidor e
páginas), não de uma chamada AppTest. O timeout anterior de 45 s não persistiu;
o resultado sustenta uma limitação temporal do ensaio local, sem demonstrar defeito
funcional do aplicativo. Não houve medição suficiente para atribuir a demora a uma
causa específica ou prometer desempenho equivalente no Cloud.

A inspeção confirmou os ajustes salvos nos dois scripts de deployment, README e
constraints. O arquivo `cloud-constraints.txt` está em UTF-8 sem BOM (primeiros
bytes `23 20 56 65 72 73`); contém somente texto ASCII válido em UTF-8. É usado
explicitamente com `-c` nos comandos de preparação do ambiente de teste. Não é
referenciado por requirements de produção nem modifica pyproject.toml. As versões
de ferramentas de reprodução estão separadas das quatro versões conhecidas do Cloud.

A verificação final derivou os caminhos Python do próprio Git e confirmou que todos
existem. O caminho correto é `src/meli_intelligence/ui/pages/executive_overview.py`,
sem barra antes de `.py`. Ruff check e format --check aprovaram os **11 arquivos
Python alterados**. `git diff --check` passou. O diff contra G31 de src, demo_data
e gerador permaneceu vazio. Ambientes, caches e evidências locais ficam fora dos
commits; o cache Python é ignorado pelo Git.

### Arquivos do checkpoint B

- `.gitattributes`
- `.gitignore`
- `demo_data/v1/manifest.json`
- `demo_data/v1/silver/sec/financial_facts.parquet`
- `demo_data/v1/silver/sec/operational_kpis.parquet`
- `docs/methodology/g36_cloud_investigation.md`
- `docs/methodology/public_demo_data_contract.md`
- `docs/methodology/public_source_review.md`
- `scripts/build_public_demo.py`
- `src/meli_intelligence/ui/domain_storytelling.py`
- `src/meli_intelligence/ui/pages/executive_overview.py`
- `src/meli_intelligence/ui/pages/financial.py`
- `src/meli_intelligence/ui/public_demo.py`
- `src/meli_intelligence/ui/temporal_charts.py`
- `tests/deployment/README.md`
- `tests/deployment/cloud-constraints.txt`
- `tests/deployment/live_contract_session.py`
- `tests/deployment/test_installed_public_update.py`
- `tests/unit/test_public_demo_bundle.py`
- `tests/unit/test_public_demo_mode.py`
- `tests/unit/test_streamlit_ux_polish.py`

### Modelos de comandos remotos — somente após aprovação, não executados

O alvo não está autorizado nem confirmado. Os placeholders abaixo não são nomes de
branches reais. Não substituir por main sob as restrições atuais. Publicar uma
branch de revisão não muda automaticamente a branch configurada no Cloud.

```powershell
# Etapa A: somente após aprovar explicitamente o alvo e o procedimento Cloud.
git -C C:\Projetos\invest-g36 push origin 41221dc86d9d4dbbc953a4b9d2c898c09c2eaa31:refs/heads/<ALVO_APROVADO>
# Etapa B: somente após homologação e aprovação separada da Etapa A.
git -C C:\Projetos\invest-g36 push origin <SHA_B_REVISADO>:refs/heads/<ALVO_APROVADO>
```

Rollback deve gerar novos commits em um checkout isolado da branch de publicação
aprovada, nunca nos dois worktrees protegidos:

```powershell
# Reverte B, mantendo instalação editável e retornando ao bundle 30/20.
git revert <SHA_B_REVISADO>
# Reverter A somente quando B estiver ausente/revertido e o bundle for o original.
git revert 41221dc86d9d4dbbc953a4b9d2c898c09c2eaa31
```

Revisar e aprovar separadamente qualquer push do rollback. Não usar force push.
A pendência operacional é homologar A no Cloud e resolver o alvo de publicação
sem violar a proibição de alterar origin/main; depois homologar B. A candidatura
local está validada, mas não se declara G36 concluído em produção.