# Independent nominal-scope audit supplements

Use **nominal-source166-external-audit-supplement-v2** for the pending final
candidate and eventual formal external checks. Candidate/database acceptance
is still pending; passing these source fixtures does not permit publication.

V2 archive SHA-256:
`6a8049abbbe928fdaccb2b8ab9a3b411a9083df9db6fb7b5d7af14e7c4f80114`.
The exact manifest SHA-256 is
`96fa4a60a40a5fa1c7830a7c8364643e710e9ae7ad5587f8432e76b4f475d27d`.
The 92,217-byte archive contains 15 source/documentation files and its manifest.
Read its [usage](nominal-source166-external-audit-supplement-v2/README.txt).

All 166 sealed source operations pass the independent interface fixture. The
78 control checks also pass after extracting the actual archive into a new
location. These include 33 subprocess attempts rejected under optimized Python;
mandatory modules explicitly reject optimization before authorization, download,
metadata access or assertion-based validation.

The source scope, precise class-case parsing and role-transition functions are
unchanged from v1. V2 adds mandatory entry guards and pins its own exact version
and file hashes. Its public runner requires a freshly downloaded archive and
full member inventory; local agent files cannot satisfy the public source proof.

V1 remains intact for review history. **Do not use it for authorization**: its
`assert __debug__` entry assertion disappears under optimization. Earlier v1
fixtures and its source manifest are preserved without being relabelled as v2.
The original eight observers in the 152 frozen build inputs remain unchanged.
These supplements have their own inventory and do not modify the database build.
