import { expect, test, type Page } from "@playwright/test";

const USUARIO = process.env.RADAR_E2E_USUARIO || "bautista";
const CLAVE = process.env.RADAR_E2E_CLAVE || "Prueba1234";

async function entrar(page: Page) {
  await page.goto("/");
  await page.getByLabel("Usuario o email").fill(USUARIO);
  await page.getByLabel("Contraseña").fill(CLAVE);
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByText("Última actualización")).toBeVisible();
}

test("ingreso con contraseña incorrecta muestra el error", async ({ page }) => {
  await page.goto("/");
  await page.getByLabel("Usuario o email").fill(USUARIO);
  await page.getByLabel("Contraseña").fill("mal-clave-1");
  await page.getByRole("button", { name: "Ingresar" }).click();
  await expect(page.getByRole("alert")).toContainText("incorrectos");
});

test("búsqueda con semáforo, detalle y selección con ficha", async ({ page, isMobile }) => {
  await entrar(page);
  await page.goto("/seleccion");
  await expect(page.getByText(/marcadas?$|Todavía no marcaste/).first()).toBeVisible();
  const vaciar = page.getByRole("button", { name: "Desmarcar todas" });
  if (await vaciar.isVisible()) {
    await vaciar.click();
    await expect(page.getByText("Todavía no marcaste propiedades")).toBeVisible();
  }
  await page.goto("/");
  if (isMobile) await page.getByRole("button", { name: "Abrir filtros" }).click();
  await page.getByLabel("Presupuesto USD").fill("160000");
  if (isMobile) await page.getByRole("button", { name: "Ver resultados" }).click();
  await expect(page.locator(".leyenda-sem")).toContainText("Verde");
  const primera = page.locator("article.res").first();
  await expect(primera).toHaveClass(/Verde/);
  await primera.click();
  await expect(page.getByRole("dialog")).toContainText("Ficha para WhatsApp");
  await page.getByRole("button", { name: "Marcar", exact: true }).click();
  await page.getByRole("button", { name: "Cerrar", exact: true }).click();
  await page.goto("/seleccion");
  await expect(page.getByText(/propiedad(es)? marcada/)).toBeVisible();
  await page.getByRole("button", { name: "Desmarcar todas" }).click();
  await expect(page.getByText("Todavía no marcaste propiedades")).toBeVisible();
});

test("mapa con puntos y zona", async ({ page }) => {
  await entrar(page);
  await page.goto("/mapa");
  await expect(page.getByText(/en el mapa/)).toBeVisible();
  await page.getByRole("button", { name: "Usar lo que se ve" }).click();
  await expect(page.getByText(/adentro/)).toBeVisible();
  await page.locator(".mapa-herr").getByRole("button", { name: "Quitar zona" }).click();
  await expect(page.getByText(/en el mapa/)).toBeVisible();
});

test("historial guarda la búsqueda", async ({ page }) => {
  await entrar(page);
  await page.goto("/historial");
  await expect(page.getByRole("tab", { name: "Búsquedas" })).toBeVisible();
  await page.getByRole("tab", { name: "Propiedades vistas" }).click();
  await expect(page.getByRole("tab", { name: "Propiedades vistas" })).toHaveAttribute("aria-selected", "true");
});

test("alta de usuario desde Equipo", async ({ page }) => {
  await entrar(page);
  await page.goto("/equipo");
  await page.getByRole("button", { name: "Nuevo usuario" }).click();
  const n = `prueba${Date.now() % 100000}`;
  await page.getByLabel("Nombre", { exact: true }).fill("Prueba");
  await page.getByLabel("Usuario (para ingresar)").fill(n);
  await page.getByRole("button", { name: "Crear usuario" }).click();
  await expect(page.getByText("Se muestra una sola vez")).toBeVisible();
  await page.getByRole("button", { name: "Listo, ya la pasé" }).click();
  await expect(page.getByText(`(${n})`)).toBeVisible();
});
