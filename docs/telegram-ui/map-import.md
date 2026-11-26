bot-ui import: 34 handlers in 11 files -> 32 screens, 11 arrows, 0 media screens, locales uk (static, read-only on the bot)

42 item(s) to review (file:line - what - default taken):
  [computed] bot.py:523 - message text is computed at run time - placeholder text; fill it in
  [computed-keyboard] bot.py:523 - cmd_start: buttons built in a loop or at run time - static buttons kept; list items are not on the map
  [computed-keyboard] bot.py:578 - choose_study_language: buttons built in a loop or at run time - static buttons kept; list items are not on the map
  [extra-message] bot.py:649 - choose_translation_language also sends a message here - the screen is the message at line 642
  [computed-keyboard] bot.py:642 - choose_translation_language: buttons built in a loop or at run time - static buttons kept; list items are not on the map
  [no-message] bot.py:659 - cmd_learn sends no message - no screen created
  [no-message] bot.py:659 - cmd_learn sends no message - no screen created
  [no-message] bot.py:665 - study_next_handler sends no message - no screen created
  [computed] bot.py:758 - message text is computed at run time - placeholder text; fill it in
  [computed] bot.py:762 - message text is computed at run time - placeholder text; fill it in
  [no-message] bot.py:826 - cmd_stats sends no message - no screen created
  [no-message] bot.py:826 - cmd_stats sends no message - no screen created
  [no-message] bot.py:901 - choose_category_handler sends no message - no screen created
  [no-message] bot.py:901 - choose_category_handler sends no message - no screen created
  [computed] bot.py:1070 - message text is computed at run time - placeholder text; fill it in
  [extra-message] bot.py:1089 - reset_confirm_handler also sends a message here - the screen is the message at line 1085
  [computed] bot.py:1101 - message text is computed at run time - placeholder text; fill it in
  [computed] bot.py:1119 - message text is computed at run time - placeholder text; fill it in
  [computed-keyboard] bot.py:1119 - home_callbacks: buttons built in a loop or at run time - static buttons kept; list items are not on the map
  [computed] bot.py:1127 - message text is computed at run time - placeholder text; fill it in
  [computed] bot.py:1138 - message text is computed at run time - placeholder text; fill it in
  [computed] bot.py:1179 - message text is computed at run time - placeholder text; fill it in
  [computed] bot.py:1188 - message text is computed at run time - placeholder text; fill it in
  [computed] bot.py:1205 - message text is computed at run time - placeholder text; fill it in
  [computed] bot.py:1207 - message text is computed at run time - placeholder text; fill it in
  [computed-keyboard] bot.py:1262 - translation_language_prompt: buttons built in a loop or at run time - static buttons kept; list items are not on the map
  [unmatched-text] bot.py:51 - reply button '🎓 Вчитися' has no F.text handler - disabled button
  [unmatched-text] bot.py:52 - reply button '📊 Статистика' has no F.text handler - disabled button
  [unmatched-text] bot.py:52 - reply button '📂 Категорії' has no F.text handler - disabled button
  [unmatched-text] bot.py:53 - reply button '⚙️ Налаштування' has no F.text handler - disabled button
  [unmatched-callback] bot.py:94 - button 'Пояснення': callback_data is computed - disabled button
  [unmatched-callback] bot.py:94 - button 'Пояснення': callback_data is computed - disabled button
  [unmatched-text] bot.py:51 - reply button '🎓 Вчитися' has no F.text handler - disabled button
  [unmatched-text] bot.py:52 - reply button '📊 Статистика' has no F.text handler - disabled button
  [unmatched-text] bot.py:52 - reply button '📂 Категорії' has no F.text handler - disabled button
  [unmatched-text] bot.py:53 - reply button '⚙️ Налаштування' has no F.text handler - disabled button
  [computed] bot.py:135 - button label is computed at run time - placeholder text; fill it in
  [computed] bot.py:140 - button label is computed at run time - placeholder text; fill it in
  [unmatched-text] bot.py:51 - reply button '🎓 Вчитися' has no F.text handler - disabled button
  [unmatched-text] bot.py:52 - reply button '📊 Статистика' has no F.text handler - disabled button
  [unmatched-text] bot.py:52 - reply button '📂 Категорії' has no F.text handler - disabled button
  [unmatched-text] bot.py:53 - reply button '⚙️ Налаштування' has no F.text handler - disabled button
