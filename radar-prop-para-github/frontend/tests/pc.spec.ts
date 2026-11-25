import { expect, test } from "@playwright/test";

const USUARIO = process.env.RADAR_E2E_USUARIO || "bautista";
const CLAVE = process.env.RADAR_E2E_CLAVE || "Prueba1234";

test.beforeEach(async ({ page, isMobile }) => {
  test.skip(!!isMobile, "solo PC");
  await page.goto("/");
  await page.getByLabel("Usuario o email").fill(USUARIO);
  await page.getByLabel("Contraseña").fill(CLAVE);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText("Revisado:")).toBeVisible();
});

test("PC: diseño de El Ojo de Dios con semáforo, detalle con crédito y selección", async ({ page }) => {
  await expect(page.locator("header")).toContainText("nuevas en 24 h");
  await expect(page.locator("aside")).toContainText("Pedido del cliente");
  await page.locator("input.c-big").fill("150000");
  await page.locator("aside .c-chip", { hasText: "Casa" }).first().click();
  await expect(page.locator(".c-pill").first()).toContainText("Verde");
  const fila = page.locator("tr.c-r.c-Verde").first();
  await fila.click();
  const det = page.locator("tr.c-det").first();
  await expect(det).toContainText("Crédito hipotecario UVA");
  await expect(det.locator(".c-cred-estado").first()).toContainText(/Califica|No califica/);
  await expect(det).toContainText("TEA");
  await fila.locator("input.c-ckp").click();
  await expect(fila.locator("input.c-ckp")).toBeChecked();
  await expect(page.locator(".c-selbar")).toContainText("1 seleccionada");
  await page.getByRole("button", { name: "Quitar selección" }).click();
  await expect(page.locator(".c-selbar")).toHaveCount(0);
});

test("PC: mapa con zona y orden por columna", async ({ page }) => {
  await page.locator(".c-bar").getByRole("button", { name: "Mapa" }).click();
  await expect(page.locator(".c-maptools")).toContainText("en el mapa");
  await page.getByRole("button", { name: "Usar lo que se ve" }).click();
  await expect(page.locator(".c-maptools")).toContainText("adentro");
  await expect(page.locator(".c-zona-activa")).toBeVisible();
  await page.getByRole("button", { name: "Borrar zona" }).click();
  await page.locator("th", { hasText: "Precio" }).first().click();
  await expect(page.locator("th", { hasText: "Precio" }).first()).toContainText("▲");
});

test("PC: simulador de crédito con líneas que califican y que no", async ({ page }) => {
  await page.locator("header").getByRole("button", { name: "Crédito UVA" }).click();
  await page.getByLabel("Valor de la propiedad").fill("300000");
  const sel = page.getByLabel("Línea de crédito");
  await expect(sel.locator("optgroup")).toHaveCount(2);
  await expect(page.locator(".c-cred-estado, .cred-estado").first()).toContainText(/Califica/);
});
