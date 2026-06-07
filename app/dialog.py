from __future__ import annotations

from typing import Callable

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
        return await step_context.prompt(
            "TextPrompt",
            PromptOptions(
                prompt=MessageFactory.text(
                    "Willkommen! Ich lege mit dir einen neuen Account an. Wie lauten dein Vor- und Nachname?"
                )
            ),
        )

    async def birthdate_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        text = step_context.result
        entities = self.extract_entities(text)
        
        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )
        
        user_profile.first_name = entities.get("first_name")
        user_profile.last_name = entities.get("last_name")

        # Fallback if NER failed to split names
        if not user_profile.first_name or not user_profile.last_name:
            parts = text.split()
            if len(parts) >= 2:
                user_profile.first_name = parts[0]
                user_profile.last_name = " ".join(parts[1:])
            else:
                user_profile.first_name = text
                user_profile.last_name = "Unknown"

        return await step_context.prompt(
            "TextPrompt",
            PromptOptions(
                prompt=MessageFactory.text("Bitte nenne dein Geburtsdatum (TT.MM.JJJJ).")
            ),
        )

    async def address_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        text = step_context.result
        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )
        
        try:
            user_profile.birthdate = validate_birthdate(text)
        except ValueError as exc:
            await step_context.context.send_activity(MessageFactory.text(str(exc)))
            return await step_context.replace_dialog("WaterfallDialog", {"step_index": 1})

        return await step_context.prompt(
            "TextPrompt",
            PromptOptions(
                prompt=MessageFactory.text(
                    "Wie lautet deine vollständige Adresse (Straße Hausnummer, PLZ Ort, Land)?"
                )
            ),
        )

    async def contact_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        text = step_context.result
        entities = self.extract_entities(text)
        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )
        
        user_profile.street = entities.get("street")
        user_profile.house_number = entities.get("house_number")
        user_profile.postal_code = entities.get("postal_code")
        user_profile.city = entities.get("city")
        user_profile.country = entities.get("country")

        return await step_context.prompt(
            "TextPrompt",
            PromptOptions(
                prompt=MessageFactory.text(
                    "Fast geschafft. Unter welcher E-Mail-Adresse und Telefonnummer bist du erreichbar?"
                )
            ),
        )

    async def summary_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        text = step_context.result
        entities = self.extract_entities(text)
        user_profile: UserProfile = await self.user_profile_accessor.get(
            step_context.context, UserProfile
        )
        
        user_profile.email = entities.get("email") or text
        user_profile.phone = entities.get("phone")

        summary = (
            f"Vielen Dank. Ich fasse zusammen:\n"
            f"- Name: {user_profile.first_name} {user_profile.last_name}\n"
            f"- Geburtsdatum: {user_profile.birthdate}\n"
            f"- Adresse: {user_profile.street} {user_profile.house_number}, {user_profile.postal_code} {user_profile.city}, {user_profile.country}\n"
            f"- E-Mail: {user_profile.email}\n"
            f"- Telefon: {user_profile.phone}\n\n"
            "Sind diese Daten korrekt?"
        )

        return await step_context.prompt(
            "ConfirmPrompt",
            PromptOptions(prompt=MessageFactory.text(summary)),
        )

    async def final_step(self, step_context: WaterfallStepContext) -> DialogTurnResult:
        if step_context.result:
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
            await step_context.context.send_activity(
                MessageFactory.text("Perfekt, dein Account wurde gespeichert. Auf Wiedersehen!")
            )
        else:
            await step_context.context.send_activity(
                MessageFactory.text("Oh, dann müssen wir wohl von vorne anfangen.")
            )

        return await step_context.end_dialog()
