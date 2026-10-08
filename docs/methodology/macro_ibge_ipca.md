# Macro Brasil — IBGE/SIDRA IPCA headline

## Escopo e fonte

Esta camada ingestiva usa exclusivamente o JSON oficial IBGE/SIDRA, tabela 1737, para o IPCA headline do Brasil. O escopo é limitado às variáveis 63 (variação mensal) e 2265 (variação acumulada em 12 meses), ambas métricas mensais distintas. A série acumulada em 12 meses é reportada pelo SIDRA e não é recalculada a partir da série mensal.

O registry fixa tabela, variável, semântica, unidade, frequência, território e URL. O parser valida o código e o rótulo de variável retornados no payload. Assim, divergência entre a resposta e os rótulos registrados interrompe a carga; uma validação online oficial não foi possível no ambiente sem conexão.

## Parsing e datas

O parser identifica no header SIDRA os campos de nível territorial, variável, período e valor, além dos pares de dimensões descritos pelo próprio header. Não depende de um número fixo para D1/D2/D3. Apenas Brasil no nível nacional é aceito.

O período mensal SIDRA `YYYYMM` vira `reference_date` no último dia calendário do mês, inclusive fevereiro em ano bissexto. Os filtros `start_date` e `end_date` são comparados por competência mensal: pedir 2023-01-01 a 2023-12-31 inclui todos os meses de 2023.

## Bronze e Macro Silver

Cada request preserva os bytes originais em Bronze, com sidecar contendo URL, tabela, variável, métrica, território, instante de coleta e SHA-256. Arquivos existentes não são sobrescritos.

Os valores normalizados entram no mesmo `macro_indicators.parquet` usado pelo pipeline BCB. A identidade de série é genérica e qualificada pela fonte: `bcb_sgs:432`, `bcb_sgs:1178`, `ibge_sidra:1737:63` e `ibge_sidra:1737:2265`. A chave econômica continua `metric_id + reference_date`.

Uma repetição com mesma chave e mesmo valor preserva o lineage existente. Se o IBGE retornar valor diferente para uma chave já gravada, o merge falha com a chave e ambos os valores: uma revisão oficial detectada interrompe o pipeline para revisão manual. Esta versão não mantém tabela histórica de revisions.

Marcadores SIDRA são tratados conforme sua semântica oficial: `...` significa valor não disponível e `..` significa não aplicável. Esses registros permanecem integralmente no Bronze, mas não produzem linha Silver. O marcador `-` significa zero absoluto e normaliza para `0.0`; `0` também é convertido numericamente para zero. Ausência nunca vira zero. Tokens inesperados, como texto vazio ou `X`, continuam falhando explicitamente. A carga exige que ambas as métricas tenham observações no intervalo solicitado antes de persistir Silver; não exige cobertura completa de toda a série histórica `p/all`.

## Limites analíticos

Os dados são observações macroeconômicas oficiais. Sua presença não implica causalidade sobre MercadoLibre, usuários, comportamento, produto ou resultados da empresa. Este sprint não calcula analytics derivados, correlações nem recomendações.
