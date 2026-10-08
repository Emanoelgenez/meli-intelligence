# Product Evidence

## Objetivo e limites

Product Evidence cria somente `HYPOTHESIS` e `QUESTION_FOR_PRODUCT_DISCOVERY`, com lineage reproduzível. A cadeia metodológica continua FACT → OBSERVATION → INTERPRETATION → PESTEL/SWOT quando aplicável → hipótese → pergunta. Hypothesis é investigável, não é fato; a pergunta busca validar, invalidar ou qualificar a hipótese. Nenhuma etapa aqui é recomendação, problema confirmado ou solução de Product.

## Regra inicial: engajamento Commerce/Fintech

A única regra desta versão exige Evidence elegível de Commerce (`unique_active_buyers_yoy_growth` ou `gmv_yoy_growth`) e Fintech (`fintech_mau_yoy_growth` ou `tpv_yoy_growth`) para o mesmo período. Valores positivos não são requisito e não determinam a hipótese. Se os dois domínios não estiverem representados no mesmo período, o builder retorna vazio. Evidências ambíguas para a mesma métrica/período falham explicitamente.

A formulação sinaliza que atividade agregada pode corresponder a padrões distintos e declara que os agregados não estabelecem overlap individual. A pergunta investiga diferenças entre grupos em nível de usuário, caso exista overlap. A hipótese não afirma que os mesmos usuários estão em Commerce e Fintech.

## Limitação de agregados

Buyers não são Fintech MAU. GMV não mede engajamento individual. TPV não mede engajamento individual. Contagens agregadas não permitem calcular overlap cross-domain, retenção cross-domain, frequência por usuário, cross-sell ou engagement por usuário. O pipeline não estima `cross_domain_user_overlap`, não soma buyers e MAU, não cria ecosystem users e não inventa índice de engagement ou proxy.

## Lineage, compatibilidade e IDs

`source_evidence_ids` é obrigatório para hipóteses e perguntas e aponta para Evidence existente. `source_interpretation_ids` contém somente registros `INTERPRETATION`. PESTEL e SWOT são opcionais; quando incluídos, seus IDs devem existir e toda a Evidence de origem deve estar contida na lineage Product. IDs de SWOT carregam também sua lineage PESTEL.

A combinação exige referência temporal compatível, incluindo data, tipo e label do período quando presentes. Chaves explícitas de definição, coorte, população e escopo não podem divergir. Mudanças de definição impedem a combinação. Uma observação temporal sem par correspondente não gera hipótese.

IDs são SHA-256 determinísticos do tipo, statement, datas e IDs de lineage. A ordenação da entrada não muda a saída. Gold usa Parquet com schema Arrow fixo, ZSTD, escrita atômica, replay idempotente e conflito fail-loud.

## Guardrails

A linguagem bloqueia causalidade, certeza de efeito, recomendação, feature, solução, roadmap, priorização e afirmações não pesquisadas de que usuários/clientes querem ou precisam algo. Perguntas precisam ser abertas e começar com How, What, Which, Where, When ou To what extent. Nenhuma pergunta inclui uma solução.

FACT, OBSERVATION, INTERPRETATION, PESTEL e SWOT fornecem contexto, mas não provam um problema de Product. A existência de uma hipótese não confirma comportamento; a pergunta não implica solução. Não há forced hypothesis: Evidence individual sem par Commerce/Fintech permanece no registry e o builder retorna vazio.
