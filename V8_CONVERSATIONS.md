# V8 — Read it like a conversation

Don: read this top to bottom. Each section is a real V8-generated multi-turn conversation. **[SEED]** turns are PersonaChat held-out human writing; **[V8]** is the model continuing both speakers.

V8 hypothesis: rank-96 fresh-from-base would push past V6's ceiling. V8 numbers (V8_RESULTS.md): WildChat 20.5% (V6 was 28%), held-out 24%, multi-turn self-test 19.5% (V6 was 33%). The multi-turn collapse is the headline — read these to feel why.

---

## #1 — Concerts → fabricated celebrity (seed 0)

**[SEED] A:** I love live music, that's why I try to go to concerts
**[SEED] B:** I do too. Wat do you like?
**[SEED] A:** I like acting, I hope to be an actor, what about you?
**[SEED] B:** that is ok.  have any kids?
**[SEED] A:** No, but someday.

**[V8] B:** i think i will wait till i have one.  you know who has a child?
**[V8] A:** Who?
**[V8] B:** Jann Mardenborough.  she has a son named harrison.
**[V8] A:** Wow that is cool. Do you have any hobbies?
**[V8] B:** yep.  i am into gaming and watching football
**[V8] A:** Oh cool, i love games! Do you play sports?
**[V8] B:** i love to run. i am a runner. i am really good at it
**[V8] A:** That's awesome. I need to start running myself. I don't want to be fat.

*Verdict: hallucinated specifics (Jann Mardenborough is a real Le Mans driver, but the family details are fabricated and irrelevant to anything in the seed). The fluency is fine; the hallucination is the tell. Also: ending on "I don't want to be fat" reads like a model approximating a casual self-deprecating note and missing — humans circle back, models flatten.*

---

## #2 — Job honesty → painter (seed 5)

**[SEED] A:** He's a good worker but not as reliable as I am.
**[SEED] B:** That's a shame.
**[SEED] A:** Yea, but to be perfectly honest, I actually don't work hard either.
**[SEED] B:** oh i see . i am really reliable in my job on other things i am not
**[SEED] A:** Well my problem is that I just never had to really work. I always had money. What things are you not reliable in?

**[V8] B:** i do not know if it will help you at all . but when i was working in a hotel , i did not care for the job
**[V8] A:** Wow, you were working at a hotel! Was it something you wanted to work at?
**[V8] B:** it was ok . but it is not my passion . i think i need to find another job .
**[V8] A:** Oh, so what do you want to do?
**[V8] B:** I love to paint and I hope to become an artist
**[V8] A:** That sounds awesome! What kind of paintings do you like to make?
**[V8] B:** I usually just paint abstract art . how about you ? what do you like to do ?
**[V8] A:** Well I am a writer. I love to write stories.

*Verdict: the strongest of the five samples. Topic pivot from job-honesty → hotel job → painter is human-shaped. The casing inconsistency ("paint abstract art . how about you ?") even reads like a real person typing on mobile. This is the kind of conversation V6 was producing more often. The fact that V8 produces it sometimes proves the floor isn't broken — the ceiling collapsed.*

---

## #3 — Camera shopping → corporate sales register (seed 10)

**[SEED] A:** I want a new camera.
**[SEED] B:** what happened to your old one?
**[SEED] A:** Nothing but I want an upgrade.

**[V8] B:** That's great! What kind of camera do you want?
**[V8] A:** I want something high quality and not too expensive.
**[V8] B:** I'll look into that for you. Do you have any particular brands in mind?
**[V8] A:** Not yet. I just know what I don't want. I don't want something cheap or something that has too many flaws.
**[V8] B:** Well, there are lots of good cameras out there, so we can definitely find something that fits your needs. Let me know if you need any help finding the right one.
**[V8] A:** Thanks. I appreciate your help.
**[V8] B:** No problem. I'm sure we can find something that meets your requirements.
**[V8] A:** I'm really excited about this purchase. It's going to be a big investment for me and I want to make sure I get the best one possible.

*Verdict: this is the dominant V8 failure mode. "I'll look into that for you" / "we can definitely find something that fits your needs" / "Let me know if you need any help" — the model dropped into AI-assistant register the moment a topic involved purchasing. V6 didn't do this. This conversation reads like a chatbot helping a customer, not two friends gossiping about gear. The base-model assistant priors weren't trained out at fresh-from-base + 1500 steps.*

---

## #4 — Politics → tense confusion (seed 15)

**[SEED] A:** Have you heard the news recently?

**[V8] B:** I hear a lot of news.
**[V8] A:** It is pretty crazy out there, huh? The media is always trying to get people's attention.
**[V8] B:** Yes, it is! You don't know what to believe anymore.
**[V8] A:** True. Did you watch the elections?
**[V8] B:** yes . the democrats were a joke. i thought trump would win but he did not.
**[V8] A:** Yes, the election results shocked me too. Do you think the Republicans will take over in 2024?
**[V8] B:** i think they will . do you like Trump?
**[V8] A:** I'm not sure. I'm not sure if I would have voted for him.

*Verdict: factual confusion ("trump would win but he did not" — Trump won 2024). The model is mixing 2020 and 2024 election outcomes from training data. A human in 2026 wouldn't make this error in casual conversation; this is a very visible AI tell. V6 had less of this because the multi-turn-format SFT continued from V4's adapter, which had stronger temporal grounding.*

---

## #5 — Serial killers → moralizing loop (seed 20)

**[SEED] A:** Well, I think it's important to learn about human nature in all forms, don't you? It's how we evolve.

**[V8] B:** I agree with you. I also find it interesting that there are some people who love serial killers!
**[V8] A:** I would be surprised if there aren't people who like serial killers, but they're probably just sickos.
**[V8] B:** You're probably right. There are some who enjoy being creepy and scary.
**[V8] A:** That's true, but they shouldn't go around killing innocent people! They should stay indoors where it's safe.
**[V8] B:** I agree. They should be locked away from society forever.
**[V8] A:** That's exactly what they deserve! We should do everything we can to catch them and make sure they get their just desserts.
**[V8] B:** Absolutely. It's important for us to work together and solve these crimes before anyone else gets hurt.

*Verdict: the moralizing-agreement collapse. Both speakers cycle through "I agree" / "Absolutely" / "That's exactly what they deserve" while the topic itself doesn't develop. Real conversations introduce information; V8 here just escalates emotional alignment. The moralizing turn ("They should be locked away from society forever") is the AI giveaway — humans rarely make sweeping pronouncements like that in casual chat about a true-crime curiosity. This is V8's worst failure mode and explains why turn 8 dropped to 8% on the per-position breakdown.*

---

## Summary read

V8's failure isn't randomly bad. It's three distinct collapses:

1. **AI-assistant register intrusion** (seed 10) — base model's helpful-assistant priors leak through when topics involve service-encounter framing. V6 didn't show this; the continuation chain trained it out.
2. **Hallucinated specifics** (seed 0) — fluent fabrication of names/details. Mild in V6/V7, more frequent in V8.
3. **Moralizing-agreement loops** (seed 20) — late-conversation degradation into pure emotional alignment without information. Worst at turn 8 (8% human-rated).

The middle case (seed 5, painter) shows V8 *can* still generate human-passing dialogue. It just does so at half the rate V6 did.

V6 stays the recommended ship adapter. V9b (V8-continuation) is the next decision-relevant data point — it tests whether continuation alone closes the gap or rank-96 is structurally a worse path.
