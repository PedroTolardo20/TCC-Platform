package com.example.ravtotem.ui

import androidx.compose.foundation.BorderStroke
import androidx.compose.foundation.Image
import androidx.compose.foundation.clickable
import androidx.compose.foundation.layout.*
import androidx.compose.foundation.lazy.grid.GridCells
import androidx.compose.foundation.lazy.grid.LazyVerticalGrid
import androidx.compose.foundation.lazy.grid.items
import androidx.compose.foundation.shape.RoundedCornerShape
import androidx.compose.material3.Button
import androidx.compose.material3.ButtonDefaults
import androidx.compose.material3.Card
import androidx.compose.material3.CardDefaults
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.Composable
import androidx.compose.ui.Alignment
import androidx.compose.ui.Modifier
import androidx.compose.ui.layout.ContentScale
import androidx.compose.ui.res.painterResource
import androidx.compose.ui.text.font.FontWeight
import androidx.compose.ui.text.style.TextAlign
import androidx.compose.ui.text.style.TextOverflow
import androidx.compose.ui.unit.dp
import com.example.ravtotem.data.Product
import com.example.ravtotem.data.formatarPreco
import com.example.ravtotem.ui.components.FuturisticBackground
import com.example.ravtotem.ui.theme.NeonCyan
import com.example.ravtotem.ui.theme.SpaceOutline
import com.example.ravtotem.ui.theme.SpaceSurface
import com.example.ravtotem.ui.theme.SpaceSurfaceHigh

@Composable
fun ProductSelectionScreen(
    products: List<Product>,
    selectedProduct: Product?,
    onProductClick: (Product) -> Unit,
    onFinalizar: () -> Unit
) {
    FuturisticBackground {
        Column(modifier = Modifier.fillMaxSize()) {
            Column(modifier = Modifier.padding(24.dp)) {
                Text(
                    text = "SELECIONE UM PRODUTO",
                    style = MaterialTheme.typography.labelLarge,
                    color = NeonCyan
                )
                Spacer(Modifier.height(4.dp))
                Text(
                    text = "O que você precisa hoje?",
                    style = MaterialTheme.typography.headlineSmall,
                    color = MaterialTheme.colorScheme.onBackground,
                    fontWeight = FontWeight.Bold
                )
            }

            LazyVerticalGrid(
                columns = GridCells.Fixed(2),
                modifier = Modifier.fillMaxSize().weight(1f),
                contentPadding = PaddingValues(horizontal = 24.dp, vertical = 8.dp),
                horizontalArrangement = Arrangement.spacedBy(16.dp),
                verticalArrangement = Arrangement.spacedBy(16.dp)
            ) {
                items(products) { product ->
                    ProductCard(
                        product = product,
                        selected = product == selectedProduct,
                        onClick = { onProductClick(product) }
                    )
                }
            }

            if (selectedProduct != null) {
                Column(modifier = Modifier.padding(24.dp)) {
                    Button(
                        onClick = onFinalizar,
                        colors = ButtonDefaults.buttonColors(
                            containerColor = NeonCyan,
                            contentColor = MaterialTheme.colorScheme.onPrimary
                        ),
                        shape = RoundedCornerShape(16.dp),
                        modifier = Modifier
                            .fillMaxWidth()
                            .height(60.dp)
                    ) {
                        Text(
                            text = "FINALIZAR PEDIDO",
                            style = MaterialTheme.typography.labelLarge,
                            fontWeight = FontWeight.Bold
                        )
                    }
                }
            }
        }
    }
}

@Composable
private fun ProductCard(product: Product, selected: Boolean, onClick: () -> Unit) {
    Card(
        modifier = Modifier
            .fillMaxWidth()
            .clickable(onClick = onClick),
        shape = RoundedCornerShape(20.dp),
        border = BorderStroke(if (selected) 2.dp else 1.dp, if (selected) NeonCyan else SpaceOutline),
        colors = CardDefaults.cardColors(
            containerColor = if (selected) SpaceSurfaceHigh else SpaceSurface
        )
    ) {
        Column(horizontalAlignment = Alignment.CenterHorizontally) {
            Image(
                painter = painterResource(id = product.imagem),
                contentDescription = product.nome,
                contentScale = ContentScale.Fit,
                modifier = Modifier
                    .fillMaxWidth()
                    .height(140.dp)
                    .padding(16.dp)
            )
            Column(
                modifier = Modifier.fillMaxWidth().padding(horizontal = 14.dp, vertical = 12.dp),
                horizontalAlignment = Alignment.CenterHorizontally
            ) {
                Text(
                    text = product.nome,
                    style = MaterialTheme.typography.titleMedium,
                    color = MaterialTheme.colorScheme.onSurface,
                    textAlign = TextAlign.Center,
                    fontWeight = FontWeight.Medium,
                    maxLines = 2,
                    overflow = TextOverflow.Ellipsis
                )
                Spacer(Modifier.height(6.dp))
                Text(
                    text = formatarPreco(product.precoCentavos),
                    style = MaterialTheme.typography.titleMedium,
                    color = NeonCyan,
                    fontWeight = FontWeight.Bold
                )
            }
        }
    }
}
