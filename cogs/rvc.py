"""
RVCInference commands cog.
"""

import os
import json
import time
import shutil
import subprocess
import requests
from discord.interactions import Interaction
from discord.ext import commands
from discord import ui
import discord
from asgiref.sync import sync_to_async
import assets.settings.setting as setting


config = json.load(
    open("assets/settings/rvc.json", "r", encoding="utf-8"))

logger = setting.logging.getLogger("rvc")

rvc_workspace = config["rvc_workspace"]


def download_audio(url, audio_format='flac', output_dir='ytdl_output', overwrite=False):
    command = [
        'yt-dlp',
        '--no-playlist',
        '--restrict-filenames',
        '--skip-download',
        '-j',  # Output info as JSON
        url,
    ]
    try:
        output = subprocess.check_output(command)
        video_info = json.loads(output)
        # Get video id
        video_id = video_info.get('id')
    except subprocess.CalledProcessError as e:
        logger.error(f"yt-dlp download error: {e.output.decode()}")
        return None
    except Exception as e:
        logger.error(e)
        return None

    output_file_path = os.path.join(output_dir, f"{video_id}.{audio_format}")

    if not overwrite:
        if os.path.exists(output_file_path):
            print("Skipping download")
            return output_file_path

    # Construct the command to be called
    command = [
        'yt-dlp',
        '--no-playlist',
        '--restrict-filenames',
        '-x',  # Extract audio
        '--audio-format', audio_format,
        '-o', os.path.join(output_dir, f'{video_id}.{audio_format}'),
        url
    ]

    # Call the command
    try:
        result = subprocess.run(
            command, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        logger.error(e)
        return None

    print('args:', result.args)

    print("Download audio end")

    return output_file_path


def vocal_split(audio_path, output_dir, model_name="HP3_all_vocals", agg=10, overwrite=False, audio_format="flac"):
    audio_path = os.path.abspath(audio_path)
    base_name = os.path.basename(audio_path)
    if model_name.endswith(".pth"):
        model_name = model_name[:-4]

    if model_name in ["HP3_all_vocals", "VR-DeEchoAggressive"]:
        vocal_expected_output_file = f"instrument_{base_name}.reformatted.wav_{agg}.flac"
        inst_expected_output_file = f"vocal_{base_name}.reformatted.wav_{agg}.flac"
    else:
        vocal_expected_output_file = f"vocal_{base_name}.reformatted.wav_{agg}.flac"
        inst_expected_output_file = f"instrument_{base_name}.reformatted.wav_{agg}.flac"

    if not overwrite:
        if os.path.exists(os.path.join(output_dir, vocal_expected_output_file)) and os.path.exists(os.path.join(output_dir, inst_expected_output_file)):
            print("Skipping vocal split")
            return os.path.join(output_dir, vocal_expected_output_file), os.path.join(output_dir, inst_expected_output_file)

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    command = ["python", "infer-web.py", "--pycmd", "python",
               "--simple_cli", "uvr", "--uvr5_weight_name", model_name,
               "--source_audio_path", audio_path, "--agg", str(agg), "--format", audio_format]

    print(f"Running command: {command}")
    try:
        result = subprocess.run(command, cwd=rvc_workspace,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        logger.error(e)
        return None, None

    print('args:', result.args)
    print('returncode:', result.returncode)
    print('stdout:', result.stdout.decode())
    print('stderr:', result.stderr.decode())

    vocal_result_path = os.path.join(output_dir, vocal_expected_output_file)
    inst_result_path = os.path.join(output_dir, inst_expected_output_file)

    try:
        shutil.move(os.path.join(rvc_workspace,
                                 "uvr5_outputs",
                                 "inst" if model_name in [
                                     "HP3_all_vocals"] else "vocal",
                                 vocal_expected_output_file),
                    vocal_result_path)
        shutil.move(os.path.join(rvc_workspace,
                                 "uvr5_outputs",
                                 "vocal" if model_name in [
                                     "HP3_all_vocals"] else "inst",
                                 inst_expected_output_file),
                    inst_result_path)
    except Exception as e:
        logger.error(f"Error while moving files after uvr inference: {e}")
        return None, None
    try:
        assert os.path.exists(
            vocal_result_path), f"Expected Vocal output file {vocal_expected_output_file} not found in {output_dir}"
        assert os.path.exists(
            inst_result_path), f"Expected Instrument output file {inst_expected_output_file} not found in {output_dir}"
    except Exception as e:
        logger.error(e)
        return None, None

    print("BGM removed successfully")

    return vocal_result_path, inst_result_path


def rvc_inference(audio_path, output_path, transposition=0, overwrite=False):
    command = ["python", "infer-web.py", "--pycmd", "python",
               "--simple_cli", "infer", "--model_file_name",
               "Ayame-Test-1.pth", "--source_audio_path",
               os.path.abspath(audio_path), "--output_file_name",
               "output.flac", "--feature_index_path",
               "logs/Ayame-Test-1/added_IVF256_Flat_nprobe_1_Ayame-Test-1_v2.index",
               "--infer_f0_method", "crepe", "--transposition", str(transposition)]

    if not overwrite:
        if os.path.exists(output_path):
            print("Skipping RVC inference")
            return os.path.abspath(output_path)

    print(f"Running command: {command}")

    try:
        result = subprocess.run(command, cwd=rvc_workspace,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        logger.error(e)
        return None

    print('args:', result.args)
    print('returncode:', result.returncode)
    print('stdout:', result.stdout.decode())
    print('stderr:', result.stderr.decode())

    output_path = os.path.abspath(output_path)
    output_folder = os.path.dirname(output_path)
    os.makedirs(output_folder, exist_ok=True)
    try:
        shutil.move(os.path.join(rvc_workspace, "audio-outputs",
                    "output.flac"), os.path.abspath(output_path))
    except Exception as e:
        logger.error(e)
        return None

    return os.path.abspath(output_path)


def convert_audio(audio_path, format):
    if format not in ["mp3", "flac", "wav"]:
        raise ValueError(f"Invalid format: {format}")

    # Construct the output file path
    base, _ = os.path.splitext(audio_path)
    output_path = f"{base}.{format}"

    # Construct the ffmpeg command
    command = ["ffmpeg", "-i", audio_path, "-y", output_path]

    # Execute the command
    try:
        subprocess.run(command, check=True)
    except Exception as e:
        logger.error(e)
        return None

    # Check that the output file was created
    assert os.path.exists(
        output_path), f"Output file was not created: {output_path}"

    return output_path


def audio_gain(audio_path, output_path, gain):
    # Make sure output_path exist
    os.makedirs(os.path.dirname(os.path.abspath(output_path)), exist_ok=True)

    # Construct the ffmpeg command
    command = ["ffmpeg", "-i", audio_path, "-af",
               f"volume={gain}dB", "-y", output_path]

    # Execute the command
    subprocess.run(command, check=True)

    # Check that the output file was created
    assert os.path.exists(
        output_path), f"Output file was not created: {output_path}"

    return output_path


def merge_tracks(*audio_file_list, output_path):
    # Construct the ffmpeg command
    command = ["ffmpeg"]

    for audio_file in audio_file_list:
        command.extend(["-i", audio_file])

    command.extend(
        ["-filter_complex", f"amix=inputs={len(audio_file_list)},pan=stereo|c0<c0+c1|c1<c0+c1", "-y", output_path])

    # Execute the command
    try:
        subprocess.run(command, check=True)
    except Exception as e:
        logger.error(e)
        return None

    # Check that the output file was created
    assert os.path.exists(
        output_path), f"Output file was not created: {output_path}"

    return output_path


def singing_conversion_cli(vocal_path, output_path, inst_path=None, transposition=0, gain=2, overwrite=False, return_vocal=False):
    infer_vocal_path = rvc_inference(
        vocal_path, f"assets/database/rvc/rvc_output/{os.path.basename(vocal_path).split('.')[0]}_rvc_output.flac", overwrite=overwrite, transposition=transposition)
    if infer_vocal_path is None:
        logger.error("RVC inference failed")
        return None, None if return_vocal else None

    if gain != 0:
        infer_vocal_path = audio_gain(
            infer_vocal_path, "assets/database/rvc/temp/gained_vocal.flac", gain)
        if infer_vocal_path is None:
            logger.error("Audio gain failed")
            return None, None if return_vocal else None

    # if inst_path is a valid file path
    if inst_path is not None and os.path.exists(inst_path):
        result_path = merge_tracks(
            infer_vocal_path, inst_path, output_path=output_path)
        if result_path is None:
            logger.error("Merge tracks failed")
            return None, None if return_vocal else None
    else:
        # Convert infer_vocal_path to mp3 and move, rename to output_path
        result_path = convert_audio(infer_vocal_path, "mp3")
        if result_path is None:
            logger.error("Convert infer vocal failed")
            return None, None if return_vocal else None
        shutil.move(result_path, output_path)
        result_path = output_path

    return (result_path, infer_vocal_path) if return_vocal else result_path


def singing_conversion_from_url(user_id, vocal_url, inst_url, output_path, transposition=0, gain=2, overwrite=False):
    # vocal_url should be a direct link to download audio file, download it and save to assets/database/rvc/upload/{user_id}/vocal_{the name of the uploaded file}.{the format of the uploaded file},
    try:
        response = requests.get(vocal_url, stream=True)
        vocal_path = f"assets/database/rvc/upload/{user_id}/vocal_{os.path.basename(vocal_url).split('.')[0]}.{os.path.basename(vocal_url).split('.')[1]}"
        os.makedirs(os.path.dirname(vocal_path), exist_ok=True)
        with open(vocal_path, "wb") as f:
            for chunk in response.iter_content(chunk_size=1024):
                if chunk:
                    f.write(chunk)
    except Exception as e:
        logger.error(e)
        return "download_failed"
    assert os.path.exists(
        vocal_path), f"Expected Vocal output file {os.path.basename(vocal_url)} not found in {vocal_path}"

    inst_path = None
    if inst_url is not None:
        try:
            response = requests.get(inst_url, stream=True)
            inst_path = f"assets/database/rvc/upload/{user_id}/inst_{os.path.basename(inst_url).split('.')[0]}.{os.path.basename(inst_url).split('.')[1]}"
            os.makedirs(os.path.dirname(inst_path), exist_ok=True)
            with open(inst_path, "wb") as f:
                for chunk in response.iter_content(chunk_size=1024):
                    if chunk:
                        f.write(chunk)
        except Exception as e:
            logger.error(e)
            return "download_failed"
        assert os.path.exists(
            inst_path), f"Expected Instrument output file {os.path.basename(inst_url)} not found in {inst_path}"

    result_path = singing_conversion_cli(
        vocal_path, output_path, inst_path, transposition, gain, overwrite)

    assert result_path == output_path, f"Expected output file {output_path} not found in {result_path}"

    if result_path is None:
        return "rvc_inference_failed"

    return result_path


def singing_conversion_from_yt(url, output_path, transposition=0, gain=2, overwrite=False, should_be_echo=True):
    start_time = time.time()
    print("Start singing conversion from youtube")
    path = download_audio(
        url, output_dir="assets/database/rvc/ytdl_outputs", overwrite=overwrite)
    if path is None:
        logger.error("Download audio failed")
        return None, None, None, None

    music_name = os.path.basename(path).split(".")[0]

    vocal_path, inst_path = vocal_split(
        audio_path=path,
        output_dir="assets/database/rvc/bgm_removed",
        model_name="HP3_all_vocals",
        agg=10,
        overwrite=overwrite,
        audio_format="flac",
    )
    if vocal_path is None or inst_path is None:
        logger.error("Vocal split failed (BGM remove)")
        return None, None, None, None

    if should_be_echo:
        vocal_path, inst_path = vocal_split(
            audio_path=path,
            output_dir="assets/database/rvc/echo_removed",
            model_name="VR-DeEchoAggressive",
            agg=10,
            overwrite=overwrite,
            audio_format="flac",
        )
        if vocal_path is None or inst_path is None:
            logger.error("Vocal split failed (Echo remove)")
            return None, None, None, None

    result_path, infer_vocal_path = singing_conversion_cli(
        vocal_path=vocal_path,
        output_path=output_path,
        inst_path=inst_path,
        transposition=transposition,
        gain=gain,
        overwrite=overwrite,
        return_vocal=True
    )
    if infer_vocal_path is None or result_path is None:
        logger.error("RVC inference failed")
        return None, None, None, None

    converted_infer_vocal_path = convert_audio(infer_vocal_path, "mp3")
    if converted_infer_vocal_path is None:
        logger.error("Convert infer vocal failed")
        return None, None, None, None

    converted_inst_path = convert_audio(inst_path, "mp3")
    if converted_inst_path is None:
        logger.error("Convert inst failed")
        return None, None, None, None

    time_elapsed = time.time() - start_time

    print(f"Time elapsed: {time_elapsed} seconds")
    print(f"Source Vocal: {converted_infer_vocal_path}")
    print(f"Source Instrumental: {converted_inst_path}")
    print(f"Result: {result_path}")

    return result_path, converted_infer_vocal_path, converted_inst_path, time_elapsed


class SingingConversionModalView(ui.View):
    def __init__(self, ctx, cog):
        self.ctx = ctx
        self.cog = cog
        super().__init__(timeout=60)

    @discord.ui.button(label="從Youtube", style=discord.ButtonStyle.danger, custom_id="singing_conversion_from_yt")
    async def convert_from_youtube(self, interaction: Interaction, button: discord.Button):
        await interaction.response.send_modal(SingingConversionModal(self.ctx, self.cog))


class SingingConversionModal(ui.Modal, title="歌聲轉換"):
    url = ui.TextInput(label="請輸入youtube連結",
                       placeholder="https://www.youtube.com/watch?v=...",
                       required=True)
    transposition = ui.TextInput(
        label="請輸入音高轉換", placeholder="男->女 12, 女->男 -12, 不變 0", default="0")
    should_de_echo = ui.TextInput(
        label="是否要對來源人聲去回音、殘響", placeholder="(y/n)", default="y")
    gain = ui.TextInput(
        label="請輸入音量增益(-20 ~ 20)", placeholder="0>>不變，1>>增加1dB，-1>>減少1db", default="2")
    overwrite = ui.TextInput(label="是否重新運算",
                             placeholder="(y/n)", default="n")

    def __init__(self, ctx, cog):
        super().__init__(timeout=60)
        self.cog = cog
        self.ctx = ctx

    async def interaction_check(self, interaction: Interaction):
        if interaction.user == self.ctx.author:
            return True
        else:
            await interaction.response.send_message("只有指令的發送者可以使用此功能", ephemeral=True)
            return False

    async def on_submit(self, interaction: Interaction):
        if self.cog.inference_lock:
            await interaction.response.send_message("正在處理，請稍後再試...", ephemeral=True)
            return
        try:
            response = requests.get(self.url.value)
            response.raise_for_status()
        except requests.HTTPError:
            await interaction.response.send_message("請輸入正確的youtube連結", ephemeral=True)
            return
        try:
            transposition_value = int(self.transposition.value)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("音高轉換必須是數字", ephemeral=True)
            return
        try:
            gain_value = int(self.gain.value)
        except Exception as e:
            logger.error(e)
            await interaction.response.send_message("音量增益必須是數字", ephemeral=True)
            return
        if gain_value > 20 or gain_value < -20:
            await interaction.response.send_message("音量增益必須介於-20到20之間", ephemeral=True)
            return
        overwrite_value = True if self.overwrite.value == "y" else False
        should_be_echo_value = True if self.should_de_echo.value == "y" else False

        await interaction.response.send_message(f"開始轉換...\n\n\t音高轉換：{transposition_value}\n\t增益：{gain_value}\n\t重新運算：{overwrite_value}\n\n來源網址：{self.url.value}")

        self.cog.inference_lock = True
        result_path, infer_vocal_path, inst_path, time_elapsed = await sync_to_async(singing_conversion_from_yt)(self.url.value, "assets/database/rvc/result.mp3", transposition_value, gain_value, overwrite_value, should_be_echo_value)
        if result_path is None or infer_vocal_path is None or inst_path is None or time_elapsed is None:
            msg = await interaction.original_response()
            await msg.edit(content="歌聲轉換失敗，請稍後再試，或者聯繫管理員")
        else:
            # Send a message to the channel
            await self.ctx.send(f"歌聲轉換完成！\n花費時間：{time_elapsed}秒", file=discord.File(result_path))
            await self.ctx.send("Vocal Only", file=discord.File(infer_vocal_path))
            await self.ctx.send("Instrument Only", file=discord.File(inst_path))
        self.cog.inference_lock = False


class RVCInferenceCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.inference_lock = False

    @commands.hybrid_command(name="歌聲轉換", description="將youtube上的歌唱音樂轉成AI角色演唱！")
    async def _rvc_singing_conversion(self, ctx, vocal_url=None, inst_url=None, transposition=0, gain=2, overwrite=False):
        if self.inference_lock:
            await ctx.send("正在處理，請稍後再試...")
            return

        # if vocal_url passed, then use CLI mode.
        if vocal_url is not None:
            # CLI Mode
            self.inference_lock = True
            async with ctx.typing():
                result_path = await sync_to_async(singing_conversion_from_url)(
                    ctx.author.id, vocal_url, inst_url, "assets/database/rvc/result.mp3", transposition, gain, overwrite
                )
            if result_path == "download_failed":
                await ctx.send("下載音樂失敗，請稍後再試，或者聯繫管理員")
            elif result_path == "rvc_inference_failed":
                await ctx.send("歌聲轉換失敗，請稍後再試，或者聯繫管理員")
            else:
                await ctx.send("歌聲轉換完成！", file=discord.File(result_path))
            self.inference_lock = False
        else:
            # GUI Mode
            await ctx.send("請選擇歌聲轉換的方式", view=SingingConversionModalView(ctx, self))


async def setup(client):
    await client.add_cog(RVCInferenceCog(client))
