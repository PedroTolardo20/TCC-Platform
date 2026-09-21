package com.example.ravplatform.data

// Dados de navegação de cada produto (propriedade do robô/ambiente, não da UI)
data class LocalProduto(
    val pontoNavegacao: String,
    val classeYolo: String
)

// id do produto -> onde ir e o que a visão deve procurar.
// IMPORTANTE: os ids DEVEM ser os mesmos do app do totem.
val catalogoNavegacao = mapOf(
    1 to LocalProduto("prateleira1", "dipirona"),
    2 to LocalProduto("prateleira2", "paracetamol"),
    3 to LocalProduto("prateleira3", "ibuprofeno"),
    4 to LocalProduto("prateleira4", "vitamina_c")
)

fun localDoProduto(produtoId: Int): LocalProduto? = catalogoNavegacao[produtoId]