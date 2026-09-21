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
    Product(1, "Dipirona 1g, 20 comprimidos", 890, R.drawable.dipirona),
    Product(2, "Paracetamol 750mg, 20 comprimidos", 1250, R.drawable.paracetamol),
    Product(3, "Ibuprofeno 400mg, 10 comprimidos", 1590, R.drawable.ibuprofeno),
    Product(4, "Vitamina C 1g efervescente", 2200, R.drawable.vitamina_c)
)