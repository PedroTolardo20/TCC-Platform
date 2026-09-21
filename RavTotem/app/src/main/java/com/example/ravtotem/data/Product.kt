package com.example.ravtotem.data

import androidx.annotation.DrawableRes
import com.example.ravtotem.R
import java.util.Locale

data class Product(
    val id: Int,
    val nome: String,
    val precoCentavos: Int,
    @DrawableRes val imagem: Int
)

// Formata centavos para "R$ 8,90" (preço em Int evita erro de ponto flutuante com dinheiro)
fun formatarPreco(centavos: Int): String =
    "R$ " + "%.2f".format(Locale.US, centavos / 100.0).replace(".", ",")

val mockProducts = listOf(
    Product(1, "Ibuprotrat 400mg, 20 comprimidos", 1390, R.drawable.ibuprotrat),
    Product(2, "Maxalgina 1g, 10 comprimidos", 990, R.drawable.maxalgina),
    Product(3, "Aciclovir 200mg, 25 comprimidos", 1790, R.drawable.aciclovir)
)