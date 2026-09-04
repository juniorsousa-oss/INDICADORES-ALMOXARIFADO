# MRP — Conversor de Relatórios

Aplicativo Streamlit para transformar relatórios brutos extraídos do ERP em dados padronizados para alimentação futura do MRP.

## Conversor v1 — RelatorioGeral

Regra principal: uma única linha por `Projeto + Código`.

- Projeto normalizado para 11 dígitos.
- Código do produto normalizado para 8 dígitos.
- `COD_MRP = PROJETO_ + CODIGO_PRODUTO`.
- Última solicitação: maior data do grupo.
- Quantidade necessária: soma do grupo.
- Quantidade atendida: soma do grupo.
- Pendência: quantidade necessária menos quantidade atendida.
- Responsáveis de separação: todos os nomes distintos.
- Data de separação: última data encontrada.
- Responsáveis de conferência: todos os nomes distintos.
- Data de conferência: última data encontrada.
- Lote não participa da chave nesta versão.

O relatório bruto não é alterado; a transformação gera uma saída tratada para conferência e exportação.

## Evolução

Novos conversores serão adicionados progressivamente conforme os relatórios brutos forem disponibilizados, preservando as regras já validadas.
