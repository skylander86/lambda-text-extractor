import subprocess
import time


def get_subprocess_output(cmdline, redirect_stderr=True, display_output_on_exception=True, logger=None, **kwargs):
    if redirect_stderr: kwargs['stderr'] = subprocess.STDOUT

    try:
        start_time = time.time()
        output = subprocess.check_output(cmdline, **kwargs)
        if logger: logger.debug('subprocess_complete', output_length=len(output), cmdline=cmdline, subprocess_args=kwargs, elapsed_time=time.time() - start_time)

        return output

    except subprocess.CalledProcessError as e:
        if display_output_on_exception and logger:
            logger.exception('subprocess_exception', output=e.output.decode('ascii', errors='ignore'), cmdline=cmdline, subprocess_args=kwargs, returncode=e.returncode)

        raise
    #end try

    return ''
#end def
