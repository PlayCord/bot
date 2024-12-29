import io

import discord


class GameStateType:
    def __init__(self):
        pass


class FieldType:
    def __init__(self, name, value, inline):
        self.name = name
        self.value = value
        self.inline = inline
        self.type = "field"
        self.limit = 25

    def _embed_transform(self, embed):
        embed.add_field(name=self.name, value=self.value, inline=self.inline)

class InfoRows:
    def __init__(self, data):


        self.data = data
        self.type = "info_rows"
        self.limit = 1

    def _embed_transform(self, embed):

        column = {}
        for person in self.data:
            for data_type in self.data[person]:
                if data_type not in column:
                    column[data_type] = {person: str(self.data[person][data_type])}
                column[data_type].update({person: str(self.data[person][data_type])})

        for data_type in column:
            for person in self.data:
                if person not in column[data_type]:
                    column[data_type].update({person: ""})
        number_names = 0
        for index in range((len(column)+(len(column)+1)//2)):


            if index % 3 == 0:

                embed.add_field(name="Name:", value="\n".join([str(p) for p in self.data.keys()]))
                number_names += 1
            else:
                embed.add_field(name=list(column.keys())[index - number_names], value="\n".join(column[list(column.keys())[index - number_names]].values()))



class ImageType:
    def __init__(self, bytes):
        self.limit = 1
        self.bytes = bytes
        self.type = "image"
        image = io.BytesIO()
        image.write(self.bytes)
        image.seek(0)
        self.game_picture = discord.File(image, filename="image.png")

    def _embed_transform(self, embed):
        # Add players and image to the embed
        embed.set_image(url="attachment://image.png")

class FooterType:

    def __init__(self, text):
        self.type = "footer"
        self.text = text
        self.limit = 1

    def _embed_transform(self, embed):
        embed.set_footer(text=self.text)

