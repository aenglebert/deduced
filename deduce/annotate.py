""" The annotate module contains the code for annotating text"""

from nltk.metrics import edit_distance

from .lookup_lists import *
from .tokenizer import join_tokens
from .utility import context
from .utility import is_initial


def annotate_names(
    text, patient_first_names, patient_initial, patient_surname, patient_given_name
):
    """This function annotates person names, based on several rules."""

    # Tokenize the text
    tokens = tokenize_split(text + " ")
    tokens_deid = []
    token_index = -1

    # Iterate over all tokens
    while token_index < len(tokens) - 1:
        # Current position
        token_index = token_index + 1

        # Current token, and number of tokens already deidentified (used to detect changes)
        token = tokens[token_index]
        num_tokens_deid = len(tokens_deid)

        # The context of this token
        (_, _, next_token, next_token_index) = context(tokens, token_index)

        ### Prefix based detection
        # Check if the token is a prefix, and the next token starts with a capital
        prefix_condition = (
            token.lower() in PREFIXES
            and next_token != ""
            and next_token[0].isupper()
            and not (len(token) > 1 and token.lower()[1] not in ['0', '1', '2', '3', '4', '5', '°']
                     and len(token) > 2 and token.lower()[2] not in ['0', '1', '2', '3', '4', '5', '°'])
            #and next_token.lower() not in WHITELIST
        )

        # If the condition is met, tag the tokens and continue to the next position
        if prefix_condition:
            tokens_deid.append(
                f"<PREFIXNAME {join_tokens(tokens[token_index:next_token_index+1])}>"
            )
            token_index = next_token_index
            continue

        ### Interfix based detection
        # Check if the token is an interfix, and the next token is in the list of interfix surnames
        interfix_condition = (
            token.lower() in INTERFIXES
            and next_token != ""
            and len(next_token) > 2
            and next_token in INTERFIX_SURNAMES
            and next_token.lower() not in WHITELIST
        )

        # If condition is met, tag the tokens and continue to the new position
        if interfix_condition:
            tokens_deid.append(
                f"<INTERFIXNAME {join_tokens(tokens[token_index])}>"
            )
            #token_index = next_token_index
            continue

        ### First name
        # Check if there is any information in the first_names variable
        if len(patient_first_names) > 1:

            # Because of the extra nested loop over first_names,
            # we can decide if the token has been tagged
            found = False

            # Voornamen
            for patient_first_name in str(patient_first_names).split(" "):
                # Check if the initials match
                if token == patient_first_name[0]:
                    # If followed by a period, also annotate the period
                    if next_token != "" and tokens[token_index + 1][0] == ".":
                        tokens_deid.append(
                            f"<INITIALPAT {join_tokens([tokens[token_index], '.'])}>"
                        )
                        if tokens[token_index + 1] == ".":
                            token_index += 1
                        else:
                            tokens[token_index + 1] = tokens[token_index + 1][1:]

                    # Else, annotate the token itself
                    else:
                        tokens_deid.append(f"<INITIALPAT {token}>")

                    # Break the first names loop
                    found = True
                    break

                # Check that either an exact match exists, or a fuzzy match
                # if the token has more than 3 characters
                first_name_condition = token.lower() == patient_first_name.lower() or (
                    len(token) > 3
                    and edit_distance(token.lower(), patient_first_name.lower(), transpositions=True)
                    <= 1
                )

                # If the condition is met, tag the token and move on
                if first_name_condition:
                    tokens_deid.append(f"<FORNAMEPAT {token}>")
                    found = True
                    break

            # If a match was found, continue
            if found:
                continue

        ### Initial
        # If the initial is not empty, and the token matches the initial, tag it as an initial
        if len(patient_initial) > 0 and token == patient_initial:
            tokens_deid.append(f"<INITIALENPAT {token}>")
            continue

        ### Surname
        if len(patient_surname) > 1:

            # Surname can consist of multiple tokens, so we will match for that
            surname_pattern = tokenize_split(patient_surname)

            # Iterate over all tokens in the pattern
            counter = 0
            match = False

            # See if there is a fuzzy match, and if there are enough tokens left
            # to match the rest of the pattern
            if edit_distance(token.lower(), surname_pattern[0].lower(), transpositions=True) <= 1 and (
                token_index + len(surname_pattern)
            ) < len(tokens):
                # Found a match
                match = True

                # Iterate over rest of pattern to see if every element matches (fuzzily)
                while counter < len(surname_pattern):

                    # If the distance is too big, disgregard the match
                    if (
                        edit_distance(
                            tokens[token_index + counter].lower(),
                            surname_pattern[counter].lower(),
                            transpositions=True,
                        )
                        > 1
                    ):

                        match = False
                        break

                    counter += 1

            # If a match was found, tag the appropriate tokens, and continue
            if match:
                tokens_deid.append(
                    f"<SURNAMEPAT {join_tokens(tokens[token_index : token_index + len(surname_pattern)])}>"
                )
                token_index = token_index + len(surname_pattern) - 1
                continue

        ### Given name
        # Match if the given name is not empty, and either the token matches exactly
        # or fuzzily when more than 3 characters long
        given_name_condition = len(patient_given_name) > 1 and (
            token == patient_given_name
            or (
                len(token) > 3
                and edit_distance(token, str(patient_given_name), transpositions=True)
                <= 1
            )
        )

        # If match, tag the token and continue
        if given_name_condition:
            tokens_deid.append(f"<GIVENNAMEPAT {token}>")
            continue

        ### Unknown first and last names
        # For both first and last names, check if the token
        # is on the lookup list and not on the whitelist
        if token in FIRST_NAMES and token.lower() not in WHITELIST:
            tokens_deid.append(f"<FORNAMEUNKNOWN {token}>")
            continue

        if token[0].isupper() and token.lower() in SURNAMES and token.lower() not in WHITELIST:
            tokens_deid.append(f"<SURNAMEUNKNOWN {token}>")
            continue

        ### Wrap up
        # Nothing has been added (ie no deidentification tag) to tokens_deid,
        # so we can safely add the token itself
        if len(tokens_deid) == num_tokens_deid:
            tokens_deid.append(token)

    # Return the deidentified tokens as a piece of text
    return join_tokens(tokens_deid).strip()


def annotate_names_context(text):
    """This function annotates person names, based on its context in the text"""

    # Tokenize text and initiate a list of deidentified tokens
    tokens = tokenize_split(text + " ")
    tokens_deid = []
    token_index = -1

    # Iterate over all tokens
    while token_index < len(tokens) - 1:

        # Current token position
        token_index = token_index + 1

        # Current token
        token = tokens[token_index]

        # Number of tokens, used to detect change
        numtokens_deid = len(tokens_deid)

        # Context of the token
        (previous_token, previous_token_index, next_token, next_token_index) = context(
            tokens, token_index
        )

        ### Initial or unknown capitalized word, detected by a name or surname that is behind it
        # If the token is an initial, or starts with a capital
        initial_condition = (
            is_initial(token)
            or (token != "" and token[0].isupper() and token.lower() not in WHITELIST)
        ) and (
            # And the token is followed by either a
            # found surname, interfix or initial
            "SURNAME" in next_token
            or "INTERFIX" in next_token
            or "INITIAL" in next_token
        )

        # If match, tag the token and continue
        if initial_condition:
            tokens_deid.append(
                f"<INITIAL {join_tokens(tokens[token_index: next_token_index + 1])}>"
            )
            token_index = next_token_index
            continue

        ### Interfix preceded by a name, and followed by a capitalized token

        # If the token is an interfix
        interfix_condition = (
                token.lower() in INTERFIXES
                and next_token != ""
                and len(next_token) > 2
                and next_token in INTERFIX_SURNAMES
                and next_token.lower() not in WHITELIST
        )

        # If the condition is met, tag the tokens and continue
        if interfix_condition:
            # Remove some already identified tokens, to prevent double tagging
            (_, previous_token_index_deid, _, _) = context(
                tokens_deid, len(tokens_deid)
            )
            deid_tokens_to_keep = tokens_deid[previous_token_index_deid:]
            tokens_deid = tokens_deid[:previous_token_index_deid]
            tokens_deid.append(
                "<INTERFIXSURNAME {}>".format(
                    join_tokens(deid_tokens_to_keep + tokens[token_index:next_token_index + 1])
                )
            )
            token_index = next_token_index
            continue

        ### Initial or name, followed by a capitalized word
        # If the token is an initial, or found name or prefix
        initial_name_condition = (
            (
                is_initial(token)
                or "FORNAME" in token
                or "GIVENNAME" in token
                or "PREFIX" in token
                # And the next token is uppercase and has at least 3 characters
            )
            and len(next_token) > 3
            and next_token[0].isupper()
            and next_token.lower() not in WHITELIST
            and (next_token in SURNAMES
                 or next_token in FIRST_NAMES
                 or next_token in INTERFIX_SURNAMES
                 )

        )

        # If a match is found, tag and continue
        if initial_name_condition:
            tokens_deid.append(
                f"<INITIALCAPITALISEDNAME {join_tokens(tokens[token_index: next_token_index + 1])}>"
            )
            token_index = next_token_index
            continue

        ### Patients A and B pattern

        # If the token is "en", and the previous token is tagged, and the next token is capitalized
        and_pattern_condition = (
            token == "et"
            and len(previous_token) > 0
            and len(next_token) > 0
            and "<" in previous_token
            and next_token[0].isupper()
        )

        # If a match is found, tag and continue
        if and_pattern_condition:
            (previous_token_deid, previous_token_index_deid, _, _) = context(
                tokens_deid, len(tokens_deid)
            )
            tokens_deid = tokens_deid[:previous_token_index_deid]
            tokens_deid.append(
                f"<MULTIPLEPERSON {join_tokens([previous_token_deid] + tokens[previous_token_index + 1 : next_token_index + 1])}>"
            )
            token_index = next_token_index
            continue

        # Nothing has been added (ie no deidentification tag) to tokens_deid,
        # so we can safely add the token itself
        if len(tokens_deid) == numtokens_deid:
            tokens_deid.append(token)

    # Join the tokens again to form the de-identified text
    textdeid = join_tokens(tokens_deid).strip()

    # Find all cap words following a name
    textdeid = re.sub("<\w*NAME\w* \w*> [A-Z]{4,}",
                      lambda pattern: "> <SURNAMEUNKNOWN".join(pattern.group().split(">")) + ">",
                      textdeid
                      )

    # If nothing changed, we are done
    if text == textdeid:
        return textdeid

    # Else, run the annotation based on context again
    return annotate_names_context(textdeid)


def annotate_residence(text):
    """Annotate residences"""

    # Tokenize text
    tokens = tokenize_split(text)
    tokens_deid = []
    token_index = -1

    # Iterate over tokens
    while token_index < len(tokens) - 1:

        # Current token position and token
        token_index = token_index + 1
        token = tokens[token_index]

        # Find all tokens that are prefixes of the remainder of the text
        prefix_matches = RESIDENCES_TRIE.find_all_prefixes(tokens[token_index:])

        # If none, just append the current token and move to the next
        if len(prefix_matches) == 0:
            tokens_deid.append(token)
            continue

        # Else annotate the longest sequence as residence
        max_list = max(prefix_matches, key=len)
        tokens_deid.append(f"<LOCATION {join_tokens(max_list)}>")
        token_index += len(max_list) - 1

    # Return the de-identified text
    text = join_tokens(tokens_deid)

    # Detect the pattern <LOCATION Saint-> <PERSON name> and convert to <LOCATION Saint-Name>
    text = re.sub('(saint|sint|st|st.)\s?-?\s?\>\s?<PERSON ',
                  lambda pattern: pattern.group().split(">")[0],
                  text,
                  flags=re.IGNORECASE)

    # Detect the pattern <LOCATION city> Saint <PERSON name> and convert to <LOCATION Saint-Name>
    text = re.sub('>\s?-?\s?(saint|sint|st|st.)\s?-?\s?\s?<PERSON ',
                  lambda pattern: pattern.group().split("<PERSON ")[0].split(">")[-1],
                  text,
                  flags=re.IGNORECASE)

    return text


def replace_altrecht_text(match: re.Match) -> str:
    """
    <INSTITUTION Altrecht> (with Altrecht in any casing) followed by words that start with capital letters is annotated
    as <INSTITUTION Altrecht Those Words>, where Altrecht retains the original casing
    :param match: the match object from a regular expression search
    :return: the final string
    """
    return match.group(0)[:len(match.group(0)) - len(match.group(1)) - 1] + match.group(1) + '>'


def annotate_institution(text):
    """Annotate institutions"""

    # Tokenize, and make a list of non-capitalized tokens (used for matching)
    tokens = tokenize_split(text)
    tokens_lower = [x.lower() for x in tokens]
    tokens_deid = []
    token_index = -1

    # Iterate over all tokens
    while token_index < len(tokens) - 1:

        # Current token position and token
        token_index = token_index + 1
        token = tokens[token_index]

        if token_index < 0 or (tokens[token_index-1] + " " + token).lower() != "examen clinique" \
                or (token + " " + tokens[token_index + 1]).lower() != "examen clinique":

            # Find all tokens that are prefixes of the remainder of the lowercasetext
            prefix_matches = INSTITUTION_TRIE.find_all_prefixes(tokens_lower[token_index:])

            # If none, just append the current token and move to the next
            if len(prefix_matches) == 0:
                tokens_deid.append(token)
                continue

            # Else annotate the longest sequence as institution
            max_list = max(prefix_matches, key=len)
            joined_institution = join_tokens(tokens[token_index:token_index + len(max_list)])
            tokens_deid.append("<INSTITUTION {}>".format(joined_institution))
            token_index += len(max_list) - 1

    # Return
    text = join_tokens(tokens_deid)

    # Detect the word "Altrecht" followed by a capitalized word
    text = re.sub('<INSTITUTION [aA][lL][tT][rR][eE][cC][hH][tT]>((\s[A-Z]([\w]*))*)',
                  replace_altrecht_text,
                  text)

    # Detect the pattern <INSTITUTION Saint-> <PERSON name> and convert to <INSTITUTION Saint-Name>
    text = re.sub('(saint|sint|st|st.)\s?-?\s?\>\s?<PERSON ',
                  lambda pattern: pattern.group().split(">")[0],
                  text,
                  flags=re.IGNORECASE)

    # Detect the pattern <INSTITUTION ... > <PERSON st name> and convert to <INSTITUTION Saint-Name>
    text = re.sub('<INSTITUTION (\w* ?)*> <PERSON (saint|sint|st|st.)',
                  lambda pattern: "".join(pattern.group().split("> <PERSON")),
                  text,
                  flags=re.IGNORECASE)

    # Return the text
    return text

def get_date_replacement_(date_match: re.Match, punctuation_name: str) -> str:
    punctuation = date_match[punctuation_name]
    if len(punctuation) != 1:
        punctuation = ' '
    return '<DATE ' + date_match.group(1) + '>' + punctuation

### Other annotation is done using a selection of finely crafted
### (but alas less finely documented) regular expressions.
def annotate_date(text):
    # Name the punctuation mark that comes after a date, for replacement purposes
    punctuation_name = 'n'

    text = re.sub("""(?ix) (0?[1-9]|[12]\d|3[01])\s?[\/]\s?[012]\d(\s?[\/]\s?(19|20)?\d{2})?|
    (0?[1-9]|[12]\d|3[01])\s?\.\s?\d{2}(\s?\.\s?\d{2,4})|
    (((Lundi|Mardi|Mercredi|Jeudi|Vendredi|Samedi|Dimanche))?
    (\d{1,2}\s)?(janvier|février|Mars|Avril|Mai|Juin|Juillet|Août|Septembre|Octobre|Novembre|Décembre)
    [\s\n\r\.,](\d{2,4})?)""",
                  lambda date_match: '<DATE ' + date_match.group() + '>',
                  text)

    text = re.sub("(\d{1,2}[^\w]{,2}(januari|februari|maart|april|mei|juni|juli|augustus|september|oktober|november|december|janvier|février|mars|avril|mai|juin|juillet|août|septembre|octobre|novembre|décembre)([- /.]{,2}(\d{4}|\d{2})){,1})(?P<" +
                  punctuation_name + ">\D)(?![^<]*>)",
                  lambda date_match: get_date_replacement_(date_match, punctuation_name),
                  text)

    text = re.sub("(19|20)\d{2}",
                  lambda date_match: '<DATE ' + date_match.group() + '>',
                  text)

    # Remove page number annotated as date
    text = re.sub("Page\s?:?\s?<DATE \d+\s*\/?\s*\d*\s*>",
                  lambda page: "".join(page.group().split('<DATE '))[:-1],
                  text,
                  flags=re.IGNORECASE)

    return text


def annotate_age(text):
    """Annotate ages"""
    text = re.sub(
        "(\d{1,3})([ -](jarige|jarig|jaar|ans))(?![^<]*>)", "<AGE \\1>\\2", text
    )
    return text


def annotate_phonenumber(text):
    """Annotate phone numbers"""
    # Belgium phone number
    text = re.sub(
        "\(?(((\+|00)32[ ]?(?:\(0\)[ ]?)?)|0)(4(60|[789]\d)\/?(\s?\d{2}\.?){2}(\s?\d{2})|(\d\/?\)?\s?\d{3}|\d{2}\/?\s?\d{2})(\.?\s?\d{2}){2})",
        lambda phone_match: '<PHONENUMBER ' + phone_match.group() + '>',
        text,
    )

    # Dutch phone number
    text = re.sub(
        "(((0)[1-9]{2}[0-9][-]?[1-9][0-9]{5})|((\\+31|0|0031)[1-9][0-9][-]?[1-9][0-9]{6}))(?![^<]*>)",
        lambda phone_match: '<PHONENUMBER ' + phone_match.group() + '>',
        text,
    )
    text = re.sub(
        "(((\\+31|0|0031)6){1}[-]?[1-9]{1}[0-9]{7})(?![^<]*>)",
        lambda phone_match: '<PHONENUMBER ' + phone_match.group() + '>',
        text,
    )

    text = re.sub(
        "((\(\d{3}\)|\d{3})\s?\d{3}\s?\d{2}\s?\d{2})(?![^<]*>)",
        lambda phone_match: '<PHONENUMBER ' + phone_match.group() + '>',
        text,
    )

    return text


def annotate_patientnumber(text, patient_id):
    """Annotate patient numbers"""

    if len(patient_id) >= 4:
        text = re.sub(patient_id, lambda patient_num : "<PATIENTNUMBER " + patient_num.group() + ">", text, re.IGNORECASE)

    text = re.sub("(\d{7,9})(?![^<]*>)", "<PATIENTNUMBER \\1>", text)
    return text


def annotate_postalcode(text):
    """Annotate postal codes"""
    text = re.sub(
        "(((\d{4} [A-Z]{2})|(\d{4}[a-zA-Z]{2})))(?P<n>\W)(?![^<]*>)",
        lambda post_code: "<LOCATION " + post_code.group() + ">",
        text,
    )

    # Belgium postcode
    text = re.sub(
        "(?:(?:[1-9])(?:\d{3}))(?!\.?\d?(\s?(m|mc|µ|c)(l|g)))",
        lambda post_code: "<LOCATION " + post_code.group() + ">",
        text,
    )
    text = re.sub("<LOCATION\s(\d{4}mg)>", "\\1", text)
    text = re.sub("([Pp]ostbus\s\d{5})", "<LOCATION \\1>", text)
    return text


def get_address_match_replacement(match: re.Match) -> str:
    text = match.group(0)
    stripped = text.strip()
    if len(text) == len(stripped):
        return f"<LOCATION {text}>"

    return f"<LOCATION {stripped}>{' ' * (len(text) - len(stripped))}"


def annotate_address(text):
    """Annotate addresses"""
    text = re.sub(
        r"([A-Z]\w+(straat|laan|hof|plein|plantsoen|gracht|kade|weg|steeg|steeg|pad|dijk|baan|dam|dreef|"
        r"kade|markt|park|plantsoen|singel|bolwerk)[\s\n\r]((\d+){1,6}(\w{0,2})?|(\d+){0,6}))",
        get_address_match_replacement,
        text,
    )

    text = re.sub(
        r"(((\d+){1,6}(\w{0,2})?|(\d+){0,6}))\s?(rue|avenue|chaussée|chemin|allée|enclos|route|cité|quai|"
        r"square|boulevard|drève|quartier|colline|impasse|promenade|rempart)"
        r"(\s(d'|de|du|des|l'|le|la|les))*\s*,?\s*[A-Z]\w+\s*,?\s*(((\d+){1,6}(\w{0,2})?|(\d+){0,6}))",
        get_address_match_replacement,
        text,
        flags=re.IGNORECASE,
    )
    return text


def merge_mail(match):
    filtered = match.group().split("<PATIENT ")[-1].split("<PERSON ")[-1]
    filtered = "".join(filtered.split(">"))
    return "<URL " + filtered + ">"


def annotate_email(text):
    """Annotate emails"""
    text = re.sub(
        "<(PATIENT |PERSON )\w+\s?>@[a-zA-Z0-9-]+(?:\.[a-zA-Z0-9-]+)*",
        merge_mail,
        text
    )

    text = re.sub(
        "[\w\d!#$%&'*+-/=?^_`{|}~]*<URL ",
        merge_mail,
        text,
    )

    text = re.sub(
        "(([\w-]+(?:\.[\w-]+)*)@((?:[\w-]+\.)*\w[\w-]{0,66})\.([a-z]{2,6}(?:\.[a-z]{2})?))(?![^<]*>)",
        "<URL \\1>",
        text,
        flags=re.IGNORECASE,
    )

    return text


def annotate_url(text):
    """Annotate urls"""
    text = re.sub(
        "((?!mailto:)(?:(?:http|https|ftp)://)(?:\\S+(?::\\S*)?@)?(?:(?:(?:[1-9]\\d?|1\\d\\d|2[01]\\d|22[0-3])(?:\\.(?:1?\\d{1,2}|2[0-4]\\d|25[0-5])){2}(?:\\.(?:[0-9]\\d?|1\\d\\d|2[0-4]\\d|25[0-4]))|(?:(?:[a-z\\u00a1-\\uffff0-9]+-?)*[a-z\\u00a1-\\uffff0-9]+)(?:\\.(?:[a-z\\u00a1-\\uffff0-9]+-?)*[a-z\\u00a1-\\uffff0-9]+)*(?:\\.(?:[a-z\\u00a1-\\uffff]{2,})))|localhost)(?::\\d{2,5})?(?:(/|\\?|#)[^\\s]*)?)(?![^<]*>)",
        "<URL \\1>",
        text,
    )

    text = re.sub(
        "([\w\d\.-]{3,}(\.)(nl|com|net|be)(/[^\s]+){,1})(?![^<]*>)", "<URL \\1>", text
    )

    return text
