const { chromium } = require("playwright");
const fs = require("node:fs/promises");
const path = require("node:path");
const assert = require("node:assert/strict");

(async () => {
  const root = new URL(process.env.DRRAS_TEST_URL).origin;
  const resultsPath = path.join(process.env.DRRAS_TEST_RESULTS, "browser_results.json");
  const browser = await chromium.launch({
    executablePath: process.env.DRRAS_BROWSER_EXECUTABLE,
    headless: true,
  });
  const context = await browser.newContext({viewport: {width: 1440, height: 1000}, locale: "en-IN"});
  await context.route("**/*", route => new URL(route.request().url()).origin === root ? route.continue() : route.abort());
  const page = await context.newPage();
  page.setDefaultTimeout(7000);
  const nav = name => page.getByRole("navigation", { name: "Main navigation" }).getByRole("button", {name, exact: true}).click();
  const text = value => page.getByText(value, {exact: true}).waitFor({state: "visible"});
  const sample = "musi-flood";
  const mapName = "Map of Musi River Flooding areas and resource bases";
  const results = [];
  async function test(id, title, ref, steps, expected, fn) {
    let actual, verdict;
    try {
      actual = await fn();
      verdict = "Pass";
    } catch (error) {
      verdict = "Fail";
      actual = error.message.split("\n").slice(0, 6).join(" ").replace(/\x1b\[[\d;]*m/g, "");
    }
    console.log(id, verdict, actual);
    results.push({id,title,ref,steps,expected,actual,verdict});
    await fs.writeFile(resultsPath, JSON.stringify(results, null, 2));
  }

  await test("BB-20", "Map before allocation and tile failure", "FR-2.1–FR-2.3 / frontend guide",
    "In Chrome, block external map-tile requests, open the dashboard, and choose Musi River Flooding. On Overview, inspect the map and fallback lists before either run.",
    "Four differently colored area markers and three base markers render before allocation. The fallback lists all affected areas and resource bases by name.", async () => {
    const response = await page.goto(root);
    assert.equal(response.status(),200);
    await page.getByRole("combobox", {name:"Select scenario"}).selectOption(sample);
    const map = page.getByRole("img", {name: mapName});
    await map.waitFor();
    const warning = "Map tiles unavailable. Area and base locations remain listed alongside the map.";
    await text(warning);
    const scenario = await (await page.request.get(root+"/api/scenarios/"+sample)).json();
    const fallback = page.getByRole("region",{name:"Map location list"});
    for (const {name} of [...scenario.areas, ...scenario.bases]) {
      await fallback.getByText(name,{exact:true}).waitFor({state:"visible"});
    }
    const colors = await map.locator("path[fill-opacity='1']").evaluateAll(nodes => nodes.map(n=>n.getAttribute("fill")));
    const bases = await map.locator(".leaflet-marker-icon").count();
    assert.deepEqual([colors.length,new Set(colors).size,bases],[4,4,3]);
    const current = await (await page.request.get(root+"/api/scenarios/"+sample+"/runs")).json();
    assert.deepEqual(current.runs,{});
    return "Four area markers used four distinct fills and three base markers appeared before any run. The tile fallback listed all four areas and three bases.";
  });

  await test("BB-21","Comparison with missing runs","FR-6.5",
    "Open Compare results on the fresh Musi sample. Go to Allocations, run Baseline, and open Compare results again.",
    "The first visit requests both methods. The baseline succeeds with a fallback notice. The second visit specifically requests Optimized.", async () => {
    await nav("Compare results");
    await text("Run the baseline and optimized allocation to see a side-by-side comparison.");
    await nav("Allocations");
    await page.getByRole("button",{name:"Run baseline",exact:true}).click();
    await text("Baseline run saved. The matrix includes straight-line estimates.");
    await nav("Compare results");
    await text("Run the optimized allocation to see a side-by-side comparison.");
    return "Initially the dashboard requested baseline and optimized. After “Baseline run saved” and its fallback notice, it requested the optimized run specifically.";
  });

  await test("BB-22","Completed comparison and page refresh","FR-6.2–FR-6.4 / FR-7.1",
    "Compare both runs for Musi, refresh, then compare a scenario where the optimizer dispatches zero ambulances.",
    "Both Musi results stay available after reload. A zero-dispatch run shows N/A for average and maximum response time and has no improvement indicator for either metric.", async () => {
    await nav("Allocations");
    await page.getByRole("button",{name:"Run optimized",exact:true}).click();
    await text("Optimized run saved. The matrix includes straight-line estimates.");
    await nav("Compare results");
    await text("Both runs saved");
    assert.equal(await page.getByRole("img",{name:mapName}).count(),2);
    const table = page.locator("main table");
    for (const name of ["Baseline","Optimized","Difference","Better when"]) await table.getByRole("columnheader",{name,exact:true}).waitFor();
    assert.equal(await table.locator("tbody tr").count(),7);
    await text("Allocation runtime");
    await text("The shared matrix includes straight-line estimates.");
    const cost = await table.getByRole("row",{name:/Total travel cost/i}).getByRole("cell").allTextContents();
    assert.equal(cost.length,5);
    await page.reload();
    await page.getByRole("combobox",{name:"Select scenario"}).selectOption(sample);
    await nav("Compare results");
    await text("Both runs saved");

    const created = await page.request.post(root+"/api/scenarios", {
      data: {name:"Regional distance check", region:"Simulated"},
    });
    assert.equal(created.status(),201);
    const {id} = await created.json();
    const endpoint = root+"/api/scenarios/"+id;
    const area = await page.request.post(endpoint+"/areas", {
      data: {name:"Affected area", location:{lat:28.6139,lng:77.209}, population:10, severity:"High", demand:1},
    });
    const base = await page.request.post(endpoint+"/bases", {
      data: {name:"Distant base", location:{lat:17.385,lng:78.4867}, quantity:1},
    });
    assert.deepEqual([area.status(),base.status()],[201,201]);
    const baseline = await page.request.post(endpoint+"/runs/baseline");
    const optimized = await page.request.post(endpoint+"/runs/optimized");
    assert.deepEqual([baseline.status(),optimized.status()],[201,201]);
    assert.equal((await baseline.json()).assignments.length,1);
    assert.equal((await optimized.json()).assignments.length,0);

    await page.reload();
    await page.getByRole("combobox",{name:"Select scenario"}).selectOption(id);
    await nav("Compare results");
    await text("Both runs saved");
    for (const label of ["Avg. response time","Max. response time"]) {
      const row = table.getByRole("row").filter({has:page.getByRole("cell",{name:label,exact:true})});
      const [, before, after, difference] = await row.getByRole("cell").allTextContents();
      assert.match(before,/ min$/);
      assert.deepEqual([after,difference],["N/A","N/A"]);
      assert.equal(await row.locator(".delta").count(),0);
    }
    await nav("Allocations");
    await page.getByRole("tab",{name:/^Optimized/}).click();
    const responseValues = page.locator(".metric-line").filter({hasText:/response time/}).locator("strong");
    assert.deepEqual(await responseValues.allTextContents(),["N/A","N/A"]);
    await page.getByRole("combobox",{name:"Select scenario"}).selectOption(sample);

    return `Musi’s ${cost[0]} showed ${cost[1]} baseline and ${cost[2]} optimized. Both runs reappeared after refresh. The zero-dispatch run showed N/A for both response times and differences, without colored indicators.`;
  });

  await test("BB-23","Travel matrix filters","FR-3.2 / FR-3.5 / frontend guide",
    "Open Travel matrix for Musi. Inspect all rows. Select Afzal Gunj, then choose OSRM road and Straight-line fallback in Estimate source.",
    "The matrix lists 12 fallback rows. Afzal Gunj gives three rows, OSRM road gives no matches, and the fallback filter restores three rows.", async () => {
    await nav("Travel matrix");
    const table = page.getByRole("table",{name:"Travel estimates from each base to each area"});
    await table.waitFor();
    const rows=table.locator("tbody tr");
    assert.equal(await rows.count(),12);
    assert.equal(await table.getByText("Straight-line fallback",{exact:true}).count(),12);
    await page.getByLabel("Affected area").selectOption({label:"Afzal Gunj"});
    assert.equal(await rows.count(),3);
    await page.getByLabel("Estimate source").selectOption({label:"OSRM road"});
    await text("No estimates match these filters.");
    await page.getByLabel("Estimate source").selectOption({label:"Straight-line fallback"});
    assert.equal(await rows.count(),3);
    return "All 12 rows were labeled Straight-line fallback. Afzal Gunj gave three rows. The road filter showed the no-match message and fallback restored the same row count.";
  });

  await test("BB-24","Open a saved run from history","FR-7.1 / frontend guide",
    "Open Run history for Musi after both runs. Check the ordering and open the baseline entry.",
    "Optimized appears above the older baseline. Opening baseline shows its stored revision and the Musi scenario snapshot.", async () => {
    await nav("Run history");
    const table = page.getByRole("table",{name:"Saved allocation runs"});
    await table.waitFor();
    const rows = table.locator("tbody tr");
    assert.equal(await rows.count(),2);
    const order = await rows.locator("td:first-child").allTextContents();
    assert.deepEqual(order,["Optimized","Baseline"]);
    await page.getByRole("button",{name:/View baseline run from revision/}).click();
    await page.getByRole("region",{name:"Saved run details"}).getByRole("heading",{name:"Baseline · Revision 1"}).waitFor();
    await page.getByRole("region",{name:"Saved run details"}).getByRole("img",{name:mapName}).waitFor();
    return "Two rows appeared newest first, Optimized then Baseline. Baseline · Revision 1 opened with the original Musi River Flooding map.";
  });
  await browser.close();
  process.exitCode = results.some(result => result.verdict !== "Pass") ? 1 : 0;
})().catch(error => { console.error(error); process.exitCode=1; });
