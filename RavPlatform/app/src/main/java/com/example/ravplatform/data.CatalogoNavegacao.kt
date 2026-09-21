package com.example.ravplatform.data

// Dados de navegação de cada produto (propriedade do robô/ambiente, não da UI)
data class LocalProduto(
    val pontoNavegacao: String,
    val classeYolo: String
)

// id do produto -> onde ir e o que a visão deve procurar.
// IMPORTANTE: os ids DEVEM ser os mesmos do app do totem.
val catalogoNavegacao = mapOf(
    1 to LocalProduto("prateleira1", "ibuprotrat"),
    2 to LocalProduto("prateleira2", "maxalgina"),
    3 to LocalProduto("prateleira3", "aciclovir")
)

fun localDoProduto(produtoId: Int): LocalProduto? = catalogoNavegacao[produtoId]

// Ponto de entrega (place): um só, igual pra todo pedido -- o braço que
// ajusta a altura de soltura por produto (ver PLACE_Z_BY_CLASS no
// start_task, lado ROS2). Precisa bater com o nome salvo no mapa do Temi.
const val PONTO_ENTREGA = "local_entrega"