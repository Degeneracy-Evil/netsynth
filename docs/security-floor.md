# NetSynth Security Floor

> Status: cross-cutting architecture constraint, not a new Scale.
>
> Security is not introduced because the network became "Scale 7". It is required because frozen Scale-5/6 semantics make ownership and authenticity claims that are meaningless in an adversarial environment unless they can be verified.

## 1. Why only a security floor

NetSynth is not becoming a general security-protocol project.

The architecture currently needs only three security properties:

1. **EID control** — a peer can verify that an actor is authorized to speak for an Endpoint ID.
2. **Binding authorization** — the Binding Service can reject unauthorized EID-to-LocatorSet changes, and readers can detect forged mapping records.
3. **Channel authentication/integrity** — Channel peers can verify each other's EID control and protect Channel state/data from undetected modification.

These properties are necessary for existing architecture semantics.

The following are explicitly outside the current security floor:

- human/user identity;
- service-name PKI;
- authorization policy for applications;
- routing-control-plane Byzantine security;
- anonymity/privacy;
- censorship resistance;
- hardware attestation;
- general capability systems;
- firewall policy;
- intrusion detection;
- secure group communication.

## 2. Prior-art reconciliation

### HIP

HIP demonstrates a self-certifying host-identity namespace. The Host Identity is a public key and the Host Identity Tag is a hash-derived operational identifier. HIP then uses authenticated Diffie-Hellman to establish peer state.

The useful lesson is that cryptographic control of a network identity can be verified end to end without requiring the routing locator to carry identity.

The direct "identity = online public key" choice is not copied because NetSynth wants identity lifetime to be longer than routine operational-key lifetime.

### SPKI/SDSI

SPKI emphasizes authorization-to-key bindings and delegation rather than forcing globally meaningful human names into the trust decision.

NetSynth adopts this principle narrowly: an Endpoint identity root may delegate specific operational roles to shorter-lived keys.

### TLS 1.3 / Noise

Modern authenticated key exchange cleanly combines ephemeral key agreement, peer authentication, transcript binding and derivation of authenticated-encryption keys.

NetSynth does not design a new cryptographic handshake primitive. It specifies the semantics that a standard AKE must bind.

### LISP-SEC

LISP explicitly requires mapping-system security and assumes/defines authorization of which entity may advertise a mapping.

NetSynth likewise treats Binding publication authorization as part of binding correctness rather than an optional add-on.

### SCION

SCION authenticates control-plane information with a PKI and signed path information.

This demonstrates the importance of infrastructure control-plane authenticity, but NetSynth deliberately does not pull the entire routing-control trust problem into this security floor.

## 3. Threat boundary

For this security floor, assume an attacker may:

- observe, replay, modify or inject Endpoint/Binding/Channel messages;
- operate ordinary network paths or caches that return stale/forged data;
- attempt to claim another EID;
- attempt to update another EID's LocatorSet;
- attempt to establish a Channel as another EID.

The architecture guarantees no availability against an on-path attacker that can simply drop traffic.

Scale-4 routing-control participants are still assumed non-Byzantine for now. Authenticating BTG/STP control objects is a separate infrastructure-security problem if/when adversarial routers enter the threat model.

## 4. Main design principle

Identity lifetime and operational-key lifetime must remain separate.

Therefore NetSynth does **not** define:

~~~text
EID = hash(current online Channel key)
~~~

Instead:

~~~text
Identity Anchor
      |
      | canonical hash
      v
     EID

Identity Anchor
      |
      +-- delegates Binding Update key(s)
      |
      +-- delegates Channel Authentication key(s)
~~~

The Anchor is long-lived and rarely used.

Operational keys may rotate without changing the EID.

## 5. What this security floor must not change

It must preserve the frozen architecture:

- Endpoint ID remains topology-independent;
- Binding still maps EID to LocatorSet;
- Scale-4 routing still operates on Locators/Route Programs;
- Channel identity still survives Locator/Route changes;
- transit routers still have no Endpoint/Channel security state;
- congestion marking remains a network soft signal.

Security should authenticate existing boundaries, not introduce another routing/naming hierarchy.

## 6. Security versus naming

Cryptographic EID control answers:

> "Is this the same cryptographic Endpoint that owns EID X?"

It does **not** answer:

> "Is EID X Alice?"
> "Is EID X example.com?"
> "Should I trust EID X to provide banking service Y?"

Human/service naming and policy trust are separate later questions.

This separation prevents the global naming system from becoming the root of basic network identity correctness.

## 7. Minimal validation target

The security-floor prototype, if built, should validate only semantic binding:

- EID derives from a stable Identity Anchor;
- rotating delegated operational keys leaves EID unchanged;
- unauthorized Binding updates fail;
- signed Binding records can be verified independently of resolver trust;
- mutually authenticated Channel establishment proves control of the two claimed EIDs;
- Channel keys remain valid across Locator/Route migration;
- forged/replayed Channel control cannot mutate Channel state;
- network congestion marks remain mutable without invalidating Channel AEAD.

It should not benchmark cryptography or invent primitives.
