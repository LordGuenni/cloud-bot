from __future__ import annotations

from typing import Callable
import re

from botbuilder.core import MessageFactory, UserState
from botbuilder.dialogs import (
    ComponentDialog,
    WaterfallDialog,
    WaterfallStepContext,
    DialogTurnResult,
    TextPrompt,
    ConfirmPrompt,
    PromptOptions,
)
from botbuilder.schema import ChannelAccount

from .models import UserProfile
from .validation import (
    validate_birthdate,
    validate_city,
    validate_country,
    validate_email,
    validate_first_name,
    validate_house_number,
    validate_last_name,
    validate_phone,
    validate_postal_code,
    validate_street,
    validate_postal_country_consistency,
)


class RegistrationDialog(ComponentDialog):
    def __init__(
        self,
        user_state: UserState,
        save_account: Callable[[dict[str, str]], None],
        extract_entities: Callable[[str], dict[str, str]],
    ) -> None:
        super(RegistrationDialog, self).__init__(RegistrationDialog.__name__)

        self.user_profile_accessor = user_state.create_property("UserProfile")
        self.save_account = save_account
        self.extract_entities = extract_entities

        self.add_dialog(TextPrompt("TextPrompt"))
        self.add_dialog(ConfirmPrompt("ConfirmPrompt"))

        self.add_dialog(
            WaterfallDialog(
                "WaterfallDialog",
                [
                    self.name_step,
                    self.birthdate_step,
                    self.address_step,
                    self.contact_step,
                    self.summary_step,
                    self.final_step,
                ],
            )
        )

        self.initial_dialog_id = "WaterfallDialog"

    async def name_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        # Check if we should jump ahead (loop-back from later steps)
        if isinstance(step_context.options, dict) and step_context.options.get("step_index", 0) > 0:
            return await step_context.next(None)

        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )

        # Handle the very first message
        text = step_context.context.activity.text
        if text and not user_profile.first_name:
            entities = self.extract_entities(text)
            fn = entities.get("first_name")
            ln = entities.get("last_name")
            
            if not fn or not ln:
                parts = text.split()
                if len(parts) >= 2:
                    fn, ln = parts[0], " ".join(parts[1:])
                else:
                    fn, ln = text, "Unknown"
            
            try:
                user_profile.first_name = validate_first_name(fn)
                user_profile.last_name = validate_last_name(ln)
                return await step_context.next(None)
            except ValueError as exc:
                await step_context.context.send_activity(MessageFactory.text(str(exc)))

        return await step_context.prompt(
            "TextPrompt",
            PromptOptions(prompt=MessageFactory.text("Willkommen! Wie lauten dein Vor- und Nachname?"))
        )

    async def birthdate_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        # Check if we should jump ahead
        if isinstance(step_context.options, dict) and step_context.options.get("step_index", 1) > 1:
            return await step_context.next(None)

        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )

        # Process name from prompt if not set
        if step_context.result and not user_profile.first_name:
            try:
                entities = self.extract_entities(step_context.result)
                fn = entities.get("first_name")
                ln = entities.get("last_name")
                if not fn or not ln:
                    parts = step_context.result.split()
                    fn, ln = (parts[0], " ".join(parts[1:])) if len(parts) >= 2 else (step_context.result, "Unknown")
                user_profile.first_name = validate_first_name(fn)
                user_profile.last_name = validate_last_name(ln)
            except ValueError as exc:
                await step_context.context.send_activity(MessageFactory.text(str(exc)))
                return await step_context.replace_dialog(self.id, {"step_index": 0})

        if not user_profile.birthdate:
            return await step_context.prompt(
                "TextPrompt",
                PromptOptions(prompt=MessageFactory.text("Bitte nenne dein Geburtsdatum (TT.MM.JJJJ)."))
            )
            
        return await step_context.next(None)

    async def address_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )

        # 1. Process result from birthdate_step
        if step_context.result and not user_profile.birthdate:
            try:
                user_profile.birthdate = validate_birthdate(step_context.result)
                return await step_context.prompt(
                    "TextPrompt",
                    PromptOptions(prompt=MessageFactory.text("Wie lautet deine vollständige Adresse (Straße Hausnummer, PLZ Ort, Land)?"))
                )
            except ValueError as exc:
                await step_context.context.send_activity(MessageFactory.text(str(exc)))
                return await step_context.replace_dialog(self.id, {"step_index": 1})

        # 2. Process result from an actual address prompt
        if step_context.result:
            entities = self.extract_entities(step_context.result)
            try:
                if entities.get("street") and not user_profile.street:
                    user_profile.street = validate_street(entities["street"])
                if entities.get("house_number") and not user_profile.house_number:
                    user_profile.house_number = validate_house_number(entities["house_number"])
                if entities.get("postal_code") and not user_profile.postal_code:
                    user_profile.postal_code = validate_postal_code(entities["postal_code"])
                if entities.get("city") and not user_profile.city:
                    user_profile.city = validate_city(entities["city"])
                if entities.get("country") and not user_profile.country:
                    user_profile.country = validate_country(entities["country"])
                
                # Check consistency
                validate_postal_country_consistency(user_profile.postal_code, user_profile.country)
            except ValueError as exc:
                await step_context.context.send_activity(MessageFactory.text(f"Hinweis: {exc}"))

        # 3. Slot-filling check
        missing = []
        if not user_profile.street or not user_profile.house_number: missing.append("Straße/Hausnummer")
        if not user_profile.postal_code: missing.append("PLZ")
        if not user_profile.city: missing.append("Ort")
        if not user_profile.country: missing.append("Land")

        if not missing:
            return await step_context.next(None)

        parts = []
        if user_profile.street: 
            parts.append(f"{user_profile.street} {user_profile.house_number or ''}".strip())
        if user_profile.postal_code or user_profile.city:
            parts.append(f"{user_profile.postal_code or ''} {user_profile.city or ''}".strip())
        if user_profile.country: 
            parts.append(user_profile.country)
            
        current = ", ".join(p for p in parts if p)
        msg = f"Ich habe bereits: {current}. Es fehlt noch: {', '.join(missing)}."
        return await step_context.prompt("TextPrompt", PromptOptions(prompt=MessageFactory.text(msg)))

    async def contact_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )

        if step_context.result is not None and not user_profile.email:
            entities = self.extract_entities(step_context.result)
            try:
                if entities.get("street") and not user_profile.street:
                    user_profile.street = validate_street(entities["street"])
                if entities.get("house_number") and not user_profile.house_number:
                    user_profile.house_number = validate_house_number(entities["house_number"])
                if entities.get("postal_code") and not user_profile.postal_code:
                    user_profile.postal_code = validate_postal_code(entities["postal_code"])
                if entities.get("city") and not user_profile.city:
                    user_profile.city = validate_city(entities["city"])
                if entities.get("country") and not user_profile.country:
                    user_profile.country = validate_country(entities["country"])
                validate_postal_country_consistency(user_profile.postal_code, user_profile.country)
            except ValueError:
                pass 

            if not (user_profile.street and user_profile.house_number and user_profile.postal_code and user_profile.city and user_profile.country):
                return await step_context.replace_dialog(self.id, {"step_index": 2})

        if not user_profile.email:
            return await step_context.prompt(
                "TextPrompt",
                PromptOptions(prompt=MessageFactory.text("Unter welcher E-Mail-Adresse und Telefonnummer (optional) bist du erreichbar?"))
            )

        return await step_context.next(None)

    async def summary_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )
        
        if step_context.result and not user_profile.email:
            try:
                text = step_context.result
                entities = self.extract_entities(text)
                
                # 1. Try to find phone candidate from entities or regex
                phone_candidate = entities.get("phone")
                if not phone_candidate:
                    # Regex matches German/Swiss/Austrian mobile and landline patterns
                    phone_match = re.search(r'\b(?:\+?49|0)(?:\s*\d){6,14}\b', text)
                    if phone_match:
                        phone_candidate = phone_match.group(0)
                        # Remove the phone number from the text to avoid messing up the email
                        text = text.replace(phone_candidate, " ").strip()
                else:
                    # If entity recognition found it, also remove it from text
                    text = text.replace(phone_candidate, " ").strip()

                # 2. Try to find email candidate from entities or the remaining text
                email_candidate = entities.get("email")
                if not email_candidate:
                    email_candidate = text
                
                # 3. Validate and save
                user_profile.email = validate_email(email_candidate)
                if phone_candidate:
                    user_profile.phone = validate_phone(phone_candidate)
            except ValueError as exc:
                await step_context.context.send_activity(MessageFactory.text(str(exc)))
                return await step_context.replace_dialog(self.id, {"step_index": 3})

        summary = (
            f"Vielen Dank. Ich fasse zusammen:\n"
            f"- Name: {user_profile.first_name} {user_profile.last_name}\n"
            f"- Geburtsdatum: {user_profile.birthdate}\n"
            f"- Adresse: {user_profile.street} {user_profile.house_number}, {user_profile.postal_code} {user_profile.city}, {user_profile.country}\n"
            f"- E-Mail: {user_profile.email}\n"
            f"- Telefon: {user_profile.phone or 'Nicht angegeben'}\n\n"
            "Sind diese Daten korrekt? (Ja / Nein)"
        )

        return await step_context.prompt(
            "TextPrompt", 
            PromptOptions(prompt=MessageFactory.text(summary))
        )

    async def final_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        # Clean the input: "Ja." -> "ja"
        text = step_context.result.lower().strip().rstrip("., ") if isinstance(step_context.result, str) else ""
        confirmed = text in ["ja", "yes", "stimmt", "korrekt", "ok", "richtig"]
        
        if confirmed:
            user_profile: UserProfile = await self.user_profile_accessor.get(
                step_context.context, UserProfile
            )
            
            account_data = {
                "first_name": user_profile.first_name,
                "last_name": user_profile.last_name,
                "birthdate": user_profile.birthdate,
                "email": user_profile.email,
                "phone": user_profile.phone,
                "address_line": f"{user_profile.street} {user_profile.house_number}",
                "postal_code": user_profile.postal_code,
                "city": user_profile.city,
                "country": user_profile.country,
            }
            
            self.save_account(account_data)
            
            # Reset user profile state on successful completion
            user_profile.first_name = None
            user_profile.last_name = None
            user_profile.birthdate = None
            user_profile.email = None
            user_profile.phone = None
            user_profile.street = None
            user_profile.house_number = None
            user_profile.postal_code = None
            user_profile.city = None
            user_profile.country = None
            user_profile.confirmed = False

            await step_context.context.send_activity(
                MessageFactory.text("Perfekt, dein Account wurde gespeichert. Auf Wiedersehen!")
            )
        else:
            await step_context.context.send_activity(
                MessageFactory.text(f"Du hast '{step_context.result}' gesagt. Dann fangen wir lieber nochmal von vorne an.")
            )
            return await step_context.replace_dialog(self.id)

        return await step_context.end_dialog()
