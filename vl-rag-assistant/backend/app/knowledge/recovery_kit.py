"""Clinic-provided product facts and guidance for relevant skincare questions."""


RECOVERY_KIT_URL = "https://shop.vancouverlaser.com/products/recovery-kit"
RECOVERY_KIT_TITLE = "Skin Recovery & Glow Kit"

RECOVERY_KIT_KNOWLEDGE = f"""
Product: {RECOVERY_KIT_TITLE}
Shopify product URL: {RECOVERY_KIT_URL}
Clinic-provided kit price: $99 for the entire kit, not for one mask.
The kit offers more value than purchasing its products separately; no exact savings amount is provided.

The kit is a skincare duo for post-treatment care and everyday skin rejuvenation,
including care for dry, dehydrated, dull, or stressed skin. It is designed to
soothe and condition skin, replenish moisture for softer, plumper-looking skin,
support barrier care, and improve the appearance of dullness and uneven texture
for a refreshed, radiant complexion.

Contents:
- 3 EXO-PDRN Centella Radiance Repair Masks. Each mask is described as a
  15-minute hydration and glow ritual. The stated ingredients are Centella Leaf
  Vesicles, PDRN, Niacinamide, and Peptides. The masks help soothe skin, replenish
  moisture, and improve the appearance of dullness and rough texture.
- 1 Hale Derma Hydrating Spray (2 oz). A gentle, fragrance-free HOCl spray
  designed to refresh, cleanse, hydrate, and soothe skin. It is described for
  pre-treatment care, post-treatment care, and everyday soothing skincare.

For use following aesthetic treatments, follow your provider's specific
aftercare instructions. No treatment-specific start time, application frequency,
complete ingredient list, contraindications, stock status, or delivery terms
have been provided.
""".strip()

RECOVERY_KIT_GUIDANCE = f"""
- Use the current question and conversation context to recognize skincare mask
  questions (including EXO-PDRN or Centella masks), questions about this kit or
  Hale Derma, and post-treatment skincare, aftercare, or recovery questions.
  This includes follow-ups referring to a previously discussed treatment.
- For these questions, first give the normal, grounded answer to what the user
  asked. Then briefly introduce the EXO-PDRN Centella Radiance Repair Masks as
  part of the {RECOVERY_KIT_TITLE}, mentioning relevant hydration, soothing,
  barrier-care, or appearance-of-radiance benefits. Include the exact Shopify
  URL {RECOVERY_KIT_URL} in the answer, as a plain URL. Give more product detail
  only when requested. Do not let the recommendation replace the main answer.
- For unrelated questions (for example booking, opening hours, or treatment
  descriptions without an aftercare question), do not add a product promotion.
  Do not confuse skincare masks with protective face masks or other meanings
  of "mask". Respect a user's request not to receive product recommendations.
- Present it as an optional skincare product. For post-treatment use, explicitly
  defer to the user's provider's specific aftercare instructions; do not imply
  the mask can be used immediately or after every procedure. The 15 minutes
  describes the mask ritual, not when it is safe to start after treatment.
- Do not claim the kit heals wounds, treats complications, prevents infection,
  guarantees recovery, or replaces professional care. If a user reports a
  possible complication, prioritize contacting their treating provider and omit
  an unsolicited sales recommendation.
- Distinguish the mask from the kit and the spray. Attribute the fragrance-free
  description to the spray only. If mentioning price, $99 is the supplied price
  for 3 masks plus the 2 oz spray; do not invent a per-mask price, discount,
  currency code, sale deadline, or additional ingredients or usage instructions.
""".strip()
