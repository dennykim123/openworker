import { expect } from "@playwright/test";
import { PROVIDERS, test } from "./fixtures";

async function openModels(page) {
  await page.goto("/");
  await page.getByTestId("account-row").click();
  await page.getByRole("button", { name: "Settings", exact: true }).click();
  await page.getByRole("button", { name: "Models", exact: true }).click();
}

for (const provider of [
  { name: "codex", ready: "ChatGPT subscription is ready" },
  { name: "claude_subscription", ready: "Claude subscription is ready" },
  { name: "gemini_subscription", ready: "Gemini subscription is ready" },
]) {
  test(`${provider.name} starts official subscription sign-in from one gallery click`, async ({ page }) => {
    const providers = PROVIDERS.map((item) => ({
      ...item,
      configured: item.name === provider.name ? false : item.configured,
    }));
    let connectPosts = 0;
    let statusChecks = 0;

    await page.route("**/v1/providers**", async (route) => {
      const request = route.request();
      const url = new URL(request.url());
      const connectPath = `/v1/providers/${provider.name}/connect`;
      if (url.pathname === "/v1/providers" && request.method() === "GET") {
        await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(providers) });
        return;
      }
      if (url.pathname === connectPath && request.method() === "POST") {
        connectPosts += 1;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true, state: "authorizing", provider: provider.name }),
        });
        return;
      }
      if (url.pathname === connectPath && request.method() === "GET") {
        statusChecks += 1;
        const item = providers.find((candidate) => candidate.name === provider.name);
        if (item) item.configured = true;
        await route.fulfill({
          status: 200,
          contentType: "application/json",
          body: JSON.stringify({ ok: true, state: "connected", provider: provider.name }),
        });
        return;
      }
      await route.fallback();
    });

    await openModels(page);
    const card = page.getByTestId(`set-provider-${provider.name}`);
    await expect(card).toContainText("Connect in one click");
    await card.click();

    await expect(page.getByTestId("set-subscription-connect")).toContainText(provider.ready, {
      timeout: 5_000,
    });
    expect(connectPosts).toBe(1);
    expect(statusChecks).toBeGreaterThan(0);
  });
}

test("missing Claude Code gets one clear official install action", async ({ page }) => {
  const providers = PROVIDERS.map((item) => ({
    ...item,
    configured: item.name === "claude_subscription" ? false : item.configured,
  }));

  await page.route("**/v1/providers**", async (route) => {
    const request = route.request();
    const path = new URL(request.url()).pathname;
    if (path === "/v1/providers" && request.method() === "GET") {
      await route.fulfill({ status: 200, contentType: "application/json", body: JSON.stringify(providers) });
      return;
    }
    if (path === "/v1/providers/claude_subscription/connect" && request.method() === "POST") {
      await route.fulfill({
        status: 200,
        contentType: "application/json",
        body: JSON.stringify({
          ok: false,
          state: "missing_runtime",
          error: "Claude Subscription is not installed yet.",
          install_url: "https://code.claude.com/docs/en/setup",
        }),
      });
      return;
    }
    await route.fallback();
  });

  await openModels(page);
  await page.getByTestId("set-provider-claude_subscription").click();
  await expect(page.getByTestId("set-subscription-install")).toHaveText(/Install official Claude Code/);
});

test("Gemini subscription shows the Google policy disclosure", async ({ page }) => {
  await openModels(page);
  await page.getByTestId("set-provider-gemini_subscription").click();
  await expect(page.getByTestId("set-subscription-connect")).toContainText(
    "Google says third-party agents must use AI Studio or Vertex AI keys",
  );
});
