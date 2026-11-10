# SchoolCafe API investigation

This records the original investigation. The implemented client now lives in `schoolmenu/provider.py`; `schoolcafe_client.py` retains CLI/import compatibility. The fixed-date default and error handling described below have since been refactored.

## Scope and evidence

The investigation used the supplied `schoolcafe_client.py` to make public, read-only requests. The client defaults select **Northeast Elementary**, grade **01**, **Lunch**, **A Line**, `PersonId=null`, and `enabledWeekendMenus=false`. These are provisional application defaults, not a confirmed choice of school or grade for the child.

Seven responses are preserved in [api_samples](api_samples/manifest.json). The manifest records URLs, school, grade, capture time, top-level keys, and SHA-256 checksums. The capture began on November 8, 2026 in America/Chicago, November 9 UTC. These are point-in-time observations of one school and grade, not a published upstream schema or a guarantee of future behavior.

| Sample | Requested date | Observed response |
| --- | --- | --- |
| Weekly | Monday, November 2 | November 2–6 |
| Weekly | Wednesday, November 4 | November 4–8 |
| Weekly | Sunday, November 8 | November 8–12 |
| Weekly | Monday, November 9 | November 9–13 |
| Weekly | Wednesday, November 11 | November 11–15 |
| Daily | Monday, November 9 | Category-to-item arrays for that date |
| Weekly | Monday, December 28 | December 28–January 1, each containing an empty object |

## 1. The weekly endpoint is a rolling five-date window

The weekly response is an object keyed by `M/D/YYYY` dates. Each value maps category names to lists of menu items:

```text
{
  "11/9/2026": {
    "ENTREES": [food, food, ...],
    "GRAINS": [food or placeholder, ...],
    ...
  },
  ...
  "11/13/2026": {...}
}
```

Despite the method's name and the client's “week containing the supplied date” docstring, a Wednesday request returned Wednesday through Sunday. Disabling weekend menus did not remove those weekend date keys.

**Application consequence:** compute the selected week's Monday before calling SchoolCafe. Request Monday, then construct and display exactly Monday through Friday. Do not request today's date directly and do not rely on the provider to select a calendar week. The application's canonical date should be an ISO calendar date; conversion to the provider's format belongs at the adapter boundary.

For example, opening on Wednesday, November 11 must request November 9. Under the updated weekend requirement, opening on Sunday, November 8 also requests November 9, the upcoming Monday.

Use the response's date keys for scheduling. Item-level `ServingDate` is an upstream timestamp, and placeholder timestamps can be `0001-01-01T06:00:00Z`.

## 2. Categories need a presentation mapping

| Observed category | Proposed presentation |
| --- | --- |
| `ENTREES` | Entrées |
| `VEGETABLE SERVED` | Vegetables, subgroup “Served vegetable” |
| `VEGETABLES CHOICE BAR` | Vegetables, subgroup “Choice bar” |
| `MILK` | Drinks |
| `FRUITS` | Fruit |
| `GRAINS` | Grains |
| `CONDIMENTS` | Omitted from the family menu |

Preserve the two vegetable subgroups so the interface does not imply all choices are necessarily interchangeable. Keep fruit and grains accessible below the main groups; condiments are intentionally omitted from the family menu. Retain unknown future categories in an “Other” group with their source labels. Categories are not a closed enum supplied by a formal contract.

Weekly items include `DisplayOrder`, but multiple items can have the same value. Use it with stable source order as the tie-breaker. Trim names for presentation without using names as identity.

## 3. Placeholder rows are not food

Empty categories can contain a full item-shaped placeholder:

```json
{
  "MenuItemId": 0,
  "PEMenuItemId": 0,
  "MenuItemDescription": "A menu has not been published for this day.",
  "Category": null,
  "ThumbnailImageURL": null,
  "ServingSizeByGrade": null,
  "Calories": 0
}
```

The original response contains additional zero and false values. A placeholder in `GRAINS` does **not** mean the entire day's menu is missing: November 9 has three real entrées and a placeholder in grains.

November 11 contains only placeholders in the sampled weekly response. The December 28 response instead contains five empty day objects. The interface must support both forms and missing date keys. None establishes that school is closed; “No menu published” is the supported statement.

Filter the recognized zero-ID sentinel before creating food entities. Treat other malformed food records as data-quality problems, not as an empty or fully reviewed menu. Placeholders must never acquire preference controls or affect the lunch calculation.

## 4. Identity differs from serving occurrence

The response exposes four relevant identifiers:

| Field | Observed use | Application handling |
| --- | --- | --- |
| `MenuItemId` | Stable for repeated foods in these samples | Canonical food identifier within a school/source scope |
| `PEMenuItemId` | Used in thumbnail URLs; also stable in these samples | Preserve as an alternate upstream identifier |
| `MenuId` | Context for a dated menu | Preserve on the serving occurrence; do not key preferences on it |
| `PEMenuId` | Additional menu context | Preserve on the serving occurrence |

For example, Popcorn Chicken has `MenuItemId=43863` and `PEMenuItemId=32008` across several dates in both sampled weeks. Skim Milk has `MenuItemId=16641` and `PEMenuItemId=15453` across both weeks. No observed `PEMenuItemId` mapped to multiple names or `MenuItemId` values in this sample set.

**Current preference key:** child profile plus `PEMenuItemId`. Live grade-1 weekly menus for Northeast and Southeast Elementary (week of 2026-11-09) share 33 normalized item names with matching `MenuItemId` and `PEMenuItemId` values; Baby Carrots specifically has `PEMenuItemId=31787` in both schools. The app keys the preference on `PEMenuItemId` so it applies across school-specific `MenuItemId` rows. This is observed behavior, not a formal provider guarantee; monitor for ID changes or reuse.

## 5. Weekly and daily data complement each other

| Field | Weekly | Daily | Presentation |
| --- | --- | --- | --- |
| `MenuItemDescription` | Yes | Yes | Food name; no separate marketing-description field was observed |
| `ServingSizeByGrade` | Yes | Yes | Serving size |
| `Calories` | Yes | Yes | Calories |
| `TotalFat` | Yes | Yes | Total fat |
| `Carbs` | Yes | Yes | Carbohydrates |
| `SatFat` | Yes | No | Saturated fat from weekly data |
| `Sodium` | Yes | No | Sodium from weekly data |
| `AllergenDisplay` | Yes, nullable | Yes, nullable | Preserve the source wording |
| `SubIngredientsDisplay` | No | Yes | Optional ingredient detail |
| `Allergens` | No | Yes | Supplementary comma-separated allergen data |
| `DefaultServingSize` | No | Yes | Optional supplementary size |
| `LastUpdatedOn` | No | Yes | Optional source revision timestamp |
| `DisplayOrder` | Yes | No | Weekly ordering |

The daily response is category-to-array directly, without a date wrapper. It omits empty categories in the November 9 sample. It is **not** a superset of the weekly response.

Render the required nutritional and allergen details immediately from weekly data. An optional daily fetch can enrich ingredients when a modal is opened. Match the serving context and both known item identifiers; merge only available enrichment fields. Do not replace the whole weekly item with the daily object or lose sodium and saturated fat. Cache the daily response so opening several foods on one date does not issue repeated daily calls.

Daily data includes `Protein`, `Milk`, `Vegetable`, `Grain`, and `Fruit`, along with `HasProtein` and other food-group flags. All those numeric fields were zero in the daily sample, including for meat and cheese items. Their semantics are not established. Do not present `Protein` as grams of protein without verification.

Daily data also includes `MyRating`, `IsMenuItemFavourite`, `AverageRatings`, and `LikesPercentage`, even though `PersonId` is null. These must **not** initialize or replace the child's local preferences. Local preferences come exclusively from SQLite.

## 6. Allergen fields require careful interpretation

Observed boolean fields include `AllergenHasMilk`, `HasWheat`, `HasSoy`, `HasEgg`, `HasPeaNuts`, `HasTreeNuts`, `HasSesame`, `HasGluten`, `HasFish`, and `HasShellFish`. Weekly data also includes `HasNuts`.

`HasMilk` is false for the sampled milk cartons even when `AllergenHasMilk` is true and `AllergenDisplay` says “Contains Milk.” The former must not be used as the milk-allergen flag.

Some text distinguishes “Contains” from “May contain.” For Cheese Pizzable, the source says “Contains Milk, Wheat. May contain Soy.” Do not flatten that into a single unqualified “contains” list. Preserve the full wording, using booleans only as supplementary source flags. Missing text or false flags must not be displayed as a verified absence of allergens. Use “Allergen information not supplied” when appropriate.

## 7. Images and descriptions have limited availability

For November 9–13, there are **47 real food occurrences**, of which **23** have `HasImage=true`. The November 2–6 sample contains 55 real occurrences, 25 with that flag.

Real items can have a nonempty `ThumbnailImageURL` even when `HasImage=false`. The weekly `Image` strings are empty in the examined real records. In a later live check, **Beef Taco Meat** had `HasImage=false` but its thumbnail endpoint returned a valid JPEG, confirming the flag can be inaccurate.

Use the allowlisted HTTPS thumbnail URL as a candidate, but do not gate the request on `HasImage`. Fetch the upstream thumbnail endpoint, decode and validate the image, and show the bundled illustration when the endpoint has no valid image. Preserve names, serving sizes, and accessible alt text without depending on photos. `MenuItemDescription` is the available description; render it as text, not HTML.

## 8. Nutrient scaling and units are verification points

`NutrientFactor` is not always 1. Observed examples include:

- Whole Grain Sweet Hawaiian Roll: factor 0.5, 110 calories, serving “1 ea.”
- Fritos Corn Chips: factor 4.0, 196 calories, serving “1 c.”
- Beef Taco Meat: factor 0.666, 98 calories, serving “2.07 oz.”
- Mini Sweet Pepper: factor 0.5, 11 calories, serving “1.14 oz.”

Display numeric nutrient values as supplied, associated with the supplied serving size. Do not apply the factor a second time based on its name. Check representative values against the provider's own menu UI during the first implementation milestone and record the outcome. The API sample does not document scaling or units. The proposed labels are calories in kcal, fats/carbohydrates in g, and sodium in mg, subject to that check. Do not invent absent nutrients, percent daily values, or convert missing values to zero.

## 9. Existing client assessment

Useful foundations are the school enum, URL encoding, timeout, request pacing, JSON-object validation, and surfaced transport errors. Reuse these rather than creating a second unrelated client.

Application integration needs explicit Monday/date selection, response normalization, typed upstream errors, injectable transport/time for tests, bounded retry policy, and persistent caching. The current fixed default `serving_date="11/9/2026"` must not determine the application's default week. The `configure()` method mutates the client; a shared instance must not be reconfigured concurrently for different schools or grades. The lock and pacing are per instance, so creating one instance per request alone will not impose a process-wide upstream rate limit.

## Verification performed for this plan

All seven JSON files parse, match their manifest keys, and match their SHA-256 checksums. Local assertions verified the rolling Wednesday window, Monday window, 47 real occurrences / 23 image flags for November 9–13, the placeholder-only Wednesday, and the fully empty December 28 week. The overlapping dates in the November 9 and November 11 weekly responses match exactly.

These are evidence checks for the investigation. They are not application tests or an application coverage report.

## Implementation follow-up

Units were checked against a [school-published SchoolCafe nutrient report](https://resources.finalsite.net/images/v1729027258/grantspassk12orus/h9z6qpsf9vwomleybxor/MenuItemNutrientsReportHSLunch.pdf), page 1: fats/carbohydrates use grams and sodium uses milligrams. The provider's [API help](https://webapis.schoolcafe.com/Help) lists additional detail and grade-discovery endpoints without explaining factor scaling or this school's grade codes. The implementation retains supplied values without additional scaling and makes the proven grade 01 configurable.

Live image verification established that `GetThumbnailImage?menuItemId=32008` returns HTTP 200 with `application/json` and a **JSON string containing base64 JPEG data**, not an image response. The implementation decodes this on the backend and serves a same-origin image route. A real response is preserved in `tests/fixtures/thumbnail.json`. Only JPEG/PNG signatures are accepted, response/decoded sizes are bounded, and an hourly bounded memory cache avoids repeated upstream requests. Missing or invalid photos use the bundled illustration.
