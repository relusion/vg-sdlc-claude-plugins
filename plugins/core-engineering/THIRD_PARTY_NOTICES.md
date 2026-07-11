# Third-Party Notices

This file accompanies the `core-engineering` plugin distribution. The plugin
contains a generated package-name corpus in these byte-identical files:

- `skills/ce-implement/scripts/popular-packages.json`
- `skills/ce-verify/scripts/popular-packages.json`
- `skills/ce-auto-build/scripts/popular-packages.json`

The corpus contains package identifiers used for offline typo-squatting checks.
It does not bundle the source code of the named packages.

## npm-high-impact

The npm portion is derived from
[`wooorm/npm-high-impact`](https://github.com/wooorm/npm-high-impact/blob/6ca165357f4cf1e127f38065455fc1c7680f8b16/lib/top-download.js)
at commit `6ca165357f4cf1e127f38065455fc1c7680f8b16`.

Modifications: the first 500 package names were extracted; JavaScript syntax,
download counts, and the remaining names were omitted; the names were combined
with identifiers from other package ecosystems in a JSON corpus.

The source is provided under the following MIT license:

> (The MIT License)
>
> Copyright (c) Titus Wormer <tituswormer@gmail.com>
>
> Permission is hereby granted, free of charge, to any person obtaining
> a copy of this software and associated documentation files (the
> 'Software'), to deal in the Software without restriction, including
> without limitation the rights to use, copy, modify, merge, publish,
> distribute, sublicense, and/or sell copies of the Software, and to
> permit persons to whom the Software is furnished to do so, subject to
> the following conditions:
>
> The above copyright notice and this permission notice shall be
> included in all copies or substantial portions of the Software.
>
> THE SOFTWARE IS PROVIDED 'AS IS', WITHOUT WARRANTY OF ANY KIND,
> EXPRESS OR IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF
> MERCHANTABILITY, FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT.
> IN NO EVENT SHALL THE AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY
> CLAIM, DAMAGES OR OTHER LIABILITY, WHETHER IN AN ACTION OF CONTRACT,
> TORT OR OTHERWISE, ARISING FROM, OUT OF OR IN CONNECTION WITH THE
> SOFTWARE OR THE USE OR OTHER DEALINGS IN THE SOFTWARE.

## Top PyPI Packages

The PyPI portion is derived from
[*Top PyPI Packages: Release 2026.07*](https://doi.org/10.5281/zenodo.21096183),
created by Hugo van Kemenade, Cal Paterson, Agriya Khetarpal, Malcolm Smith,
Martin Thoma, Mike Fiedler, Richard Si, Stan Ulbrych, and Zsolt Dollenstein.
The dataset is licensed under
[Creative Commons Attribution 4.0 International](https://creativecommons.org/licenses/by/4.0/)
(CC BY 4.0).

Modifications: the first 500 `project` values were extracted; download counts,
other metadata, and the remaining rows were omitted; the names were combined
with identifiers from other package ecosystems in a JSON corpus.

## Registry-derived identifiers

The corpus also contains package identifiers obtained from the
[NuGet Search Query Service](https://learn.microsoft.com/en-us/nuget/api/search-query-service-resource),
subject to the [NuGet Terms of Use](https://www.nuget.org/policies/Terms), and
from the crates.io API under its
[Data Access policy](https://rust-lang.github.io/rfcs/3463-crates-io-policy-update.html#data-access),
plus a project-maintained list of Go module identifiers. The source URLs and
generation date are recorded inside each `popular-packages.json` file. These
entries identify packages only; no package implementation is copied.

> [!WARNING]
> The current generator does not yet enforce crates.io's one-request-per-second
> limit while paging. Do not regenerate the corpus until that implementation is
> corrected. Reading the committed corpus makes no registry request.

Package names and other third-party marks remain the property of their
respective owners. Their use is for identification and does not imply
affiliation or endorsement. No Apache-2.0 license grant is asserted over rights
owned by third parties.
