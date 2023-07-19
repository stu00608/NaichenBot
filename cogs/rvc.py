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
from concurrent.futures import ThreadPoolExecutor
import assets.settings.setting as setting


config = json.load(
    open("assets/settings/rvc.json", "r", encoding="utf-8"))

logger = setting.logging.getLogger("rvc")

dataset_cleaner_workspace = config["dataset_cleaner_workspace"]
rvc_workspace = config["rvc_workspace"]

executor = ThreadPoolExecutor(max_workers=5)


def download_audio(url, audio_format='flac', output_dir='ytdl_output', overwrite=False):
    command = [
        'yt-dlp',
        '--no-playlist',
        '--skip-download',
        '-j',  # Output info as JSON
        url,
    ]
    try:
        output = subprocess.check_output(command)
        video_info = json.loads(output)
        title = video_info.get('title')
    except subprocess.CalledProcessError as e:
        logger.error(f"yt-dlp download error: {e.output.decode()}")
        return None
    except Exception as e:
        logger.error(e)
        return None

    output_file_path = os.path.join(output_dir, f"{title}.{audio_format}")
    output_file_path = output_file_path.replace(" ", "_")

    if not overwrite:
        if os.path.exists(output_file_path):
            print("Skipping download")
            return output_file_path

    # Construct the command to be called
    command = [
        'yt-dlp',
        '-x',  # Extract audio
        '--audio-format', audio_format,
        '-o', os.path.join(output_dir, '%(title)s.%(ext)s'),
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

    # Remove spaces from the file name
    os.rename(os.path.join(
        output_dir, f"{title}.{audio_format}"), output_file_path)

    print("Download audio end")

    return output_file_path


def vocal_split(audio_path, output_dir, model_name="HP3_all_vocals.pth", agg=10, overwrite=False):
    audio_path = os.path.abspath(audio_path)
    base_name = os.path.basename(audio_path)
    vocal_expected_output_file = f"vocal_{base_name}_{agg}.flac"
    inst_expected_output_file = f"instrument_{base_name}_{agg}.flac"

    if not overwrite:
        if os.path.exists(os.path.join(output_dir, vocal_expected_output_file)) and os.path.exists(os.path.join(output_dir, inst_expected_output_file)):
            print("Skipping vocal split")
            return os.path.join(output_dir, vocal_expected_output_file), os.path.join(output_dir, inst_expected_output_file)

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    command = ["python", "dataset_cleaner.py", "remove_bgm", "--input_dir",
               audio_path, "--output_dir", output_dir, "--model_name", model_name, "--agg", str(agg), "--export_both"]
    print(f"Running command: {command}")
    try:
        result = subprocess.run(command, cwd=dataset_cleaner_workspace,
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
    assert os.path.exists(
        vocal_result_path), f"Expected Vocal output file {vocal_expected_output_file} not found in {output_dir}"
    assert os.path.exists(
        inst_result_path), f"Expected Instrument output file {inst_expected_output_file} not found in {output_dir}"

    print("BGM removed successfully")

    return vocal_result_path, inst_result_path


def vocal_echo_remove(audio_path, output_dir, agg=10, overwrite=False):
    audio_path = os.path.abspath(audio_path)
    base_name = os.path.basename(audio_path)
    vocal_expected_output_file = f"vocal_{base_name}_{agg}.flac"

    if not overwrite:
        if os.path.exists(os.path.join(output_dir, vocal_expected_output_file)):
            print("Skipping echo removal")
            return os.path.join(output_dir, vocal_expected_output_file)

    output_dir = os.path.abspath(output_dir)
    os.makedirs(output_dir, exist_ok=True)
    command = ["python", "dataset_cleaner.py", "remove_echo", "--input_dir",
               audio_path, "--output_dir", output_dir, "--agg", str(agg)]
    print(f"Running command: {command}")
    try:
        result = subprocess.run(command, cwd=dataset_cleaner_workspace,
                                stdout=subprocess.PIPE, stderr=subprocess.PIPE)
    except Exception as e:
        logger.error(e)
        return None

    print('args:', result.args)
    print('returncode:', result.returncode)
    print('stdout:', result.stdout.decode())
    print('stderr:', result.stderr.decode())

    vocal_result_path = os.path.join(output_dir, vocal_expected_output_file)
    assert os.path.exists(
        vocal_result_path), f"Expected Vocal output file {vocal_expected_output_file} not found in {output_dir}"

    print("Echo removed successfully")

    return vocal_result_path


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
    shutil.move(os.path.join(rvc_workspace, "audio-outputs",
                "output.flac"), os.path.abspath(output_path))
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
               f"volume={gain}", "-y", output_path]

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


def singing_conversion_from_yt(url, output_path, transposition=0, gain=2, overwrite=False):
    start_time = time.time()
    print("Start singing conversion from youtube")
    path = download_audio(
        url, output_dir="assets/database/rvc/ytdl_outputs", overwrite=overwrite)
    if path is None:
        logger.error("Download audio failed")
        return None, None, None, None

    music_name = os.path.basename(path).split(".")[0]

    vocal_path, inst_path = vocal_split(
        path, "assets/database/rvc/bgm_removed", overwrite=overwrite)
    if vocal_path is None or inst_path is None:
        logger.error("Vocal split failed")
        return None, None, None, None

    clean_vocal_path = vocal_echo_remove(
        vocal_path, "assets/database/rvc/echo_removed", overwrite=overwrite)
    if clean_vocal_path is None:
        logger.error("Echo remove failed")
        return None, None, None, None

    infer_vocal_path = rvc_inference(
        clean_vocal_path, f"assets/database/rvc/rvc_output/{music_name}_rvc_output.flac", overwrite=overwrite, transposition=transposition)
    if infer_vocal_path is None:
        logger.error("RVC inference failed")
        return None, None, None, None

    gained_infer_vocal_path = audio_gain(
        infer_vocal_path, "assets/database/rvc/temp/gained_vocal.flac", gain)
    if gained_infer_vocal_path is None:
        logger.error("Audio gain failed")
        return None, None, None, None

    result_path = merge_tracks(
        gained_infer_vocal_path, inst_path, output_path=output_path)
    if result_path is None:
        logger.error("Merge tracks failed")
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
        label="請輸入音高轉換(男->女 12, 女->男 -12, 不變 0)", placeholder="0", default="0")
    gain = ui.TextInput(label="請輸入音量增益", placeholder="2", default="2")
    overwrite = ui.TextInput(label="請輸入是否覆蓋(y/n)", placeholder="n", default="n")

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

        # TODO: Make a embed to show the preview of youtube video.
        await interaction.response.send_message(f"開始轉換...\n\n\t音高轉換：{transposition_value}\n\t增益：{gain_value}\n\t重新運算：{overwrite_value}\n\n來源網址：{self.url.value}")

        self.cog.inference_lock = True
        result_path, infer_vocal_path, inst_path, time_elapsed = await sync_to_async(singing_conversion_from_yt)(self.url.value, "assets/database/rvc/result.mp3", transposition_value, gain_value, overwrite_value)
        if result_path is None or infer_vocal_path is None or inst_path is None or time_elapsed is None:
            msg = await interaction.original_response()
            await msg.edit(content="歌聲轉換失敗，請稍後再試，或者聯繫管理員")
        else:
            # Send a message to the channel
            await self.ctx.send(f"歌聲轉換完成！\n花費時間：{time_elapsed}秒", file=discord.File(result_path))
            await self.ctx.send("Vocal Only", file=discord.File(infer_vocal_path))
            await self.ctx.send("Instrument Only", file=discord.File(inst_path))
        self.cog.inference_lock = False
        # future = executor.submit(
        #     singing_conversion_from_yt, self.url.value, "assets/database/rvc/result.mp3", transposition_value, gain_value, overwrite_value)
        # future.add_done_callback(self.singing_conversion_from_yt_callback)

    def singing_conversion_from_yt_callback(self, future):
        result_path, infer_vocal_path, inst_path, time_elapsed = future.result()

        if result_path is None or infer_vocal_path is None or inst_path is None or time_elapsed is None:
            self.cog.bot.loop.create_task(self.send_msg_to_channel(
                self.ctx, "歌聲轉換失敗，請稍後再試，或者聯繫管理員"))
        else:
            self.cog.bot.loop.create_task(self.send_result_to_channel(
                self.ctx, result_path, infer_vocal_path, inst_path, time_elapsed))
            # Send the file from result_path to the channel
        self.cog.inference_lock = False

    async def send_msg_to_channel(self, ctx, msg):
        await ctx.send(msg)

    async def send_result_to_channel(self, ctx, result_path, infer_vocal_path, inst_path, time_elapsed):
        await ctx.send(
            f"歌聲轉換完成！", file=discord.File(result_path))
        await ctx.send(
            f"原始音檔：", file=discord.File(infer_vocal_path))
        await ctx.send(
            f"原始伴奏：", file=discord.File(inst_path))
        await ctx.send(
            f"花費時間：{time_elapsed}秒"
        )


class RVCInferenceCog(commands.Cog):

    def __init__(self, bot):
        self.bot = bot
        self.inference_lock = False

    @commands.hybrid_command(name="歌聲轉換", description="將youtube上的歌唱音樂轉成AI角色演唱！")
    async def _rvc_singing_conversion(self, ctx):
        if self.inference_lock:
            await ctx.send("正在處理，請稍後再試...")
            return
        await ctx.send("請選擇歌聲轉換的方式", view=SingingConversionModalView(ctx, self))

    # TODO: Implement a version is to upload vocal and instrumental file to discord and do the inference
    # (it should be able to inference without instrumental file, then just return vocal back).


async def setup(client):
    await client.add_cog(RVCInferenceCog(client))
