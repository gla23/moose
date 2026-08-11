# Email on the domain, via iCloud+

Getting `hello@graciousmoosedesigns.com` sending and receiving properly, using the iCloud+
subscription we already pay for. Custom email domains are included on **every**
iCloud+ tier, including the £0.99/mo 50 GB one — there's no email-specific upgrade.

Checked 11 August 2026 against Apple's documentation. Limits do change; the sources
are at the bottom.

---

## How it actually works

Apple's model is "personalise the mailbox you already have", not "host a mail
server". You keep one iCloud mailbox; the custom domain becomes an additional
identity that mail arrives at and can be sent from. There's no separate account,
no separate password, no separate inbox to check.

### The two limits that both happen to be five

This is the bit that's easy to misread — **both numbers are 5, and they mean
different things**:

- **Up to 5 custom domains** per iCloud+ subscription.
- **Up to 5 other people** you can share any one domain with — family, or anyone
  else since iOS 16. Each of them uses it from their own Apple Account.

And then separately:

- **Up to 3 active email addresses per person, per domain.**

So for one domain used alone, that's **3 addresses** (`hello@`, `orders@`,
`amaris@`, say). Shared with 5 other people, it's 6 people × 3 = **18 addresses**
on that domain, but each person only controls their own three and they land in
that person's own mailbox.

Worth being clear: the 3-address limit is the one likely to bite, not the domain
count. If more than three aliases are needed on the domain, the catch-all is the
way round it.

### Catch-all

The domain owner can choose to **accept mail sent to addresses that aren't set up**.
With that on, `anything@graciousmoosedesigns.com` reaches the inbox without pre-registering it —
useful for `info@`, `sales@`, one-off addresses per supplier, and so on. It also
means spam to guessed addresses gets through, so it's a trade-off rather than a
default-on.

### Requirements

- An active **iCloud+** subscription (any tier).
- **Two-factor authentication** on the Apple Account.
- **iCloud Mail switched on** — there has to be an existing `@icloud.com` mailbox
  for the domain to attach to.
- A domain you own, **with access to its DNS**.

### The domain can only serve one mail provider

Mail delivery is decided by the domain's MX records, and there's one set of them.
Pointing MX at iCloud means iCloud is the mail host for that domain, full stop —
you can't also run Cloudflare Email Routing, Zoho, or anything else on it. DNS can
stay wherever it is; it's specifically the MX records that are exclusive.

### Sending limits — this is not a mailing-list tool

iCloud Mail is a personal mailbox and is rate-limited as one:

| Limit | Value |
|---|---|
| Messages per day | 1,000 |
| Recipients per day | 1,000 |
| Recipients per message | 500 |
| Message size | 20 MB (up to 5 GB via Mail Drop) |

Fine for customer correspondence. **Not** for the "Join My Mailing List" signups —
bulk sending from a personal mailbox gets the domain's reputation burned. If that
list is ever used, it wants a proper email service with unsubscribe handling.

### It depends on the subscription staying active

If iCloud+ lapses, mail already received stays readable, but **incoming mail to the
custom addresses starts bouncing back to senders** and you can't send from them.
It's not a graceful degradation — worth knowing before putting the address on
printed material or Etsy listings.

---

## Setup

### 1. Add the domain in iCloud

**iCloud.com → Mail → Settings (⚙) → Custom Email Domain → Add.**

Choose *a domain you already own*, then whether it's only you or shared. Enter the
domain, then the address you want. Apple immediately generates the DNS records —
including a verification value unique to this domain.

### 2. Add the DNS records

Apple shows you the exact values. **Use what Apple shows you** — the table below is
what to expect, and the `apple-domain` value in particular is unique to you:

| Type | Name | Value | Priority |
|---|---|---|---|
| MX | `@` | `mx01.mail.icloud.com` | 10 |
| MX | `@` | `mx02.mail.icloud.com` | 10 |
| TXT | `@` | `apple-domain=<your unique code>` | — |
| TXT | `@` | `v=spf1 redirect=icloud.com` | — |
| CNAME | `sig1._domainkey` | `sig1.dkim.graciousmoosedesigns.com.at.icloudmailadmin.com` | — |

What each one is doing, because it helps when something fails:

- **The two MX records** tell other mail servers where to deliver mail for the
  domain. Equal priority (10) means the two hosts are alternatives — either will
  do, which is redundancy rather than ordering.
- **`apple-domain=…` TXT** is proof you control the domain. Apple looks this value
  up before it will accept mail for you, so nobody can claim a domain they don't own.
  It's checked at setup, and should be left in place.
- **The SPF record** publishes which servers are allowed to send as your domain.
  Note it's `v=spf1 redirect=icloud.com`, **not** the far more common
  `include:…` — `redirect=` hands the whole policy over to Apple's record rather
  than merging one clause into yours. Don't "fix" it to `include:`, and don't add a
  second SPF record: a domain may only have one, and two is a hard failure rather
  than a merge.
- **The DKIM CNAME** points at a public key Apple hosts. Apple signs outgoing mail
  with the matching private key, and the recipient fetches the key at
  `sig1._domainkey.graciousmoosedesigns.com` to verify the signature. This is what stops your
  mail being trivially spoofable, and it's the reason a real mailbox provider beats
  a forwarding-plus-relay arrangement.

### 3. Cloudflare specifics

Three things to get right, in order of how often they break this:

1. **Proxy OFF (grey cloud) on the DKIM CNAME.** A proxied CNAME gets flattened and
   answered by Cloudflare's own edge, so the lookup no longer returns Apple's key
   and every signature fails verification. This is the single most common cause of
   iCloud custom-domain problems. MX and TXT records can't be proxied anyway, so
   this only applies to the CNAME.
2. **Don't enable Cloudflare Email Routing on this domain** — it rewrites the MX
   records to Cloudflare's own, which silently takes delivery away from iCloud.
3. **Disable Cloudflare's parked-domain landing page**, which otherwise sits in
   front of the records and stops them taking effect. Cloudflare documents this as
   a prerequisite.

Apple's automated DNS setup only supports a handful of registrars, so on Cloudflare
these go in by hand. About ten minutes.

### 4. Verify

Back in iCloud, hit verify. Usually a few minutes; occasionally up to an hour,
which is DNS propagation rather than anything being wrong. If it fails, the
verification TXT and the DKIM CNAME are the two to re-check first.

### 5. Make it the sending identity

Adding the domain doesn't change what you send *from*. In **Mail → Settings →
Accounts → iCloud → Email Address**, set the new address as the default outgoing
identity, otherwise replies keep going out as `@icloud.com`.

Third-party clients (Thunderbird, or Gmail's "Send mail as" via Apple's SMTP) need
an **app-specific password** generated at appleid.apple.com — the main Apple Account
password won't authenticate.

---

## Afterwards

### The site already points here

`CONTACT_EMAIL` in `build.py` is set to `hello@graciousmoosedesigns.com`, and both
forms build a pre-filled message to it. **So create that mailbox specifically** —
until it exists, anything a visitor sends will bounce. It's the first of the three
addresses the domain allows.

### Prove the authentication actually works

Don't assume it. Send a message to a Gmail address and a Microsoft one, then look
at the raw headers (in Gmail: **⋮ → Show original**). You want:

```
spf=pass
dkim=pass
```

Both passing means the domain is properly authenticated and mail should reach
inboxes rather than spam. `dkim=fail` almost always means the CNAME is proxied.

### Consider adding DMARC

Apple sets up SPF and DKIM but **not** DMARC, which is the record that tells
receivers what to do when a message fails those checks — and gets you reports on
who's sending as your domain. Without it, the two checks pass but nothing is
enforced. Start in monitoring mode:

```
Type: TXT   Name: _dmarc   Value: v=DMARC1; p=none; rua=mailto:hello@graciousmoosedesigns.com
```

`p=none` changes no delivery behaviour, it just turns on reporting. After a few
weeks of clean reports, tighten to `p=quarantine` and eventually `p=reject`. Going
straight to `p=reject` risks binning legitimate mail you'd forgotten about.

### DNS coexistence with the website

The mail records and the GitHub Pages records live side by side without conflict —
MX governs mail, A/CNAME govern web traffic:

| Purpose | Type | Name | Value |
|---|---|---|---|
| Site (apex) | A | `@` | `185.199.108.153`, `.109.153`, `.110.153`, `.111.153` |
| Site (www) | CNAME | `www` | `<user>.github.io` |
| Mail | MX / TXT / CNAME | as above | as above |

Keep the Pages records **DNS only** (grey cloud) too, so GitHub can complete its
certificate challenge.

The domain is **graciousmoosedesigns.com**, which Cloudflare Registrar does sell, so
registration and DNS can both sit there if you'd rather keep them together.

## Sources

- [Apple — Use a custom email domain with iCloud Mail](https://support.apple.com/en-gb/102540)
- [Apple — Personalise iCloud Mail with a custom email domain and share with others](https://support.apple.com/guide/icloud/icloud-custom-email-domain-mme8ed800b5d/icloud)
- [Apple — Mailbox size and message sending limits in iCloud](https://support.apple.com/en-us/102198)
- [Apple — Stop using a custom domain](https://support.apple.com/guide/icloud/stop-using-a-domain-mmaca557cdf1/icloud)
- [Apple — iCloud+ plans and pricing (UK)](https://www.apple.com/uk/icloud/)
- [Cloudflare Registrar — iCloud custom email domains](https://developers.cloudflare.com/registrar/account-options/icloud-domains/)
- [Porkbun — configuring a domain for iCloud hosted email](https://kb.porkbun.com/article/199-how-to-configure-your-domain-to-icloud-hosted-email)
